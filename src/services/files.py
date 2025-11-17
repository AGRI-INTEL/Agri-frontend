"""
Service de gestion des fichiers avec support multi-stockage
"""

import os
import uuid
import hashlib
import mimetypes
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, BinaryIO, Tuple
from pathlib import Path

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
import aiofiles
# Make PIL and magic library imports optional
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    Image = None
    PIL_AVAILABLE = False

try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    magic = None
    MAGIC_AVAILABLE = False

from config.config import get_settings
from config.database import get_db
from api.models.sql.files import (
    FileShare, FileAttachment, FileFolder, FileFolderItem,
    FilePermission, FileActivity, FileType, FileStatus, StorageProvider
)
from api.models.sql.user import User
from api.schemas.files import (
    FileResponse, FileCreate, FileUpdate, FolderResponse,
    FileUploadRequest, FileStats, FileSearchParams
)

settings = get_settings()


class FileValidationError(Exception):
    """Exception pour les erreurs de validation de fichiers"""
    pass


class StorageService:
    """Service de stockage de fichiers"""
    
    def __init__(self):
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration des types de fichiers autorisés
        self.allowed_types = {
            'image': ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'],
            'video': ['video/mp4', 'video/avi', 'video/mov', 'video/wmv', 'video/webm'],
            'audio': ['audio/mp3', 'audio/wav', 'audio/ogg', 'audio/m4a'],
            'document': [
                'application/pdf', 'text/plain', 'text/csv',
                'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            ],
            'archive': ['application/zip', 'application/x-rar-compressed', 'application/x-7z-compressed']
        }
        
        # Taille maximale par type (en octets)
        self.max_sizes = {
            'image': 10 * 1024 * 1024,  # 10MB
            'video': 100 * 1024 * 1024,  # 100MB
            'audio': 50 * 1024 * 1024,   # 50MB
            'document': 25 * 1024 * 1024,  # 25MB
            'archive': 100 * 1024 * 1024,   # 100MB
            'other': 10 * 1024 * 1024      # 10MB
        }
    
    def validate_file(self, file: UploadFile, file_type: FileType) -> None:
        """Valide un fichier avant upload"""
        
        # Vérifier la taille
        max_size = self.max_sizes.get(file_type.value, self.max_sizes['other'])
        if file.size and file.size > max_size:
            raise FileValidationError(f"Fichier trop volumineux. Taille maximale: {max_size // (1024*1024)}MB")
        
        # Vérifier le type MIME
        allowed_mimes = []
        for mime_list in self.allowed_types.values():
            allowed_mimes.extend(mime_list)
        
        if file.content_type not in allowed_mimes:
            raise FileValidationError(f"Type de fichier non autorisé: {file.content_type}")
        
        # Vérifier l'extension
        file_ext = Path(file.filename).suffix.lower()
        dangerous_extensions = ['.exe', '.bat', '.cmd', '.scr', '.pif', '.vbs', '.js']
        if file_ext in dangerous_extensions:
            raise FileValidationError(f"Extension de fichier dangereuse: {file_ext}")
    
    def determine_file_type(self, mime_type: str) -> FileType:
        """Détermine le type de fichier basé sur le MIME type"""
        
        for file_type, mime_types in self.allowed_types.items():
            if mime_type in mime_types:
                return FileType(file_type)
        
        return FileType.OTHER
    
    def generate_filename(self, original_name: str, user_id: str) -> str:
        """Génère un nom de fichier unique"""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_uuid = str(uuid.uuid4())[:8]
        file_ext = Path(original_name).suffix.lower()
        
        return f"{user_id}_{timestamp}_{file_uuid}{file_ext}"
    
    async def save_file(self, file: UploadFile, filename: str) -> Tuple[str, str]:
        """Sauvegarde un fichier sur le disque"""
        
        # Créer la structure de dossiers par date
        date_path = datetime.now().strftime("%Y/%m/%d")
        full_dir = self.upload_dir / date_path
        full_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = full_dir / filename
        storage_url = f"/static/{date_path}/{filename}"
        
        # Sauvegarder le fichier
        async with aiofiles.open(file_path, 'wb') as out_file:
            content = await file.read()
            await out_file.write(content)
        
        return str(file_path), storage_url
    
    async def delete_file(self, file_path: str) -> bool:
        """Supprime un fichier du disque"""
        
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
        except Exception as e:
            print(f"Erreur suppression fichier {file_path}: {e}")
        
        return False
    
    def extract_metadata(self, file_path: str, mime_type: str) -> Dict[str, Any]:
        """Extrait les métadonnées d'un fichier"""
        
        metadata = {}
        
        # Skip metadata extraction if magic library is not available
        if not MAGIC_AVAILABLE:
            return metadata
        
        try:
            if mime_type.startswith('image/'):
                metadata.update(self._extract_image_metadata(file_path))
            elif mime_type.startswith('video/'):
                metadata.update(self._extract_video_metadata(file_path))
            elif mime_type.startswith('audio/'):
                metadata.update(self._extract_audio_metadata(file_path))
        
        except Exception as e:
            print(f"Erreur extraction métadonnées: {e}")
        
        return metadata
    
    def _extract_image_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extrait les métadonnées d'une image"""
        
        try:
            with Image.open(file_path) as img:
                return {
                    'width': img.width,
                    'height': img.height,
                    'format': img.format,
                    'mode': img.mode,
                    'has_transparency': img.mode in ('RGBA', 'LA') or 'transparency' in img.info
                }
        except Exception:
            return {}
    
    def _extract_video_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extrait les métadonnées d'une vidéo"""
        # TODO: Implémenter avec ffmpeg-python
        return {}
    
    def _extract_audio_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extrait les métadonnées d'un fichier audio"""
        # TODO: Implémenter avec mutagen
        return {}


class FileService:
    """Service principal de gestion des fichiers"""
    
    def __init__(self):
        self.storage = StorageService()
    
    async def upload_file(
        self,
        file: UploadFile,
        user_id: str,
        upload_request: FileUploadRequest,
        db: AsyncSession
    ) -> FileResponse:
        """Upload un fichier"""
        
        try:
            # Déterminer le type de fichier
            file_type = self.storage.determine_file_type(file.content_type)
            
            # Valider le fichier
            self.storage.validate_file(file, file_type)
            
            # Générer le nom de fichier
            filename = self.storage.generate_filename(file.filename, user_id)
            
            # Sauvegarder le fichier
            file_path, storage_url = await self.storage.save_file(file, filename)
            
            # Extraire les métadonnées
            metadata = self.storage.extract_metadata(file_path, file.content_type)
            
            # Créer l'enregistrement en base
            file_record = FileShare(
                original_name=file.filename,
                filename=filename,
                mime_type=file.content_type,
                file_type=file_type,
                file_size=file.size or 0,
                file_path=file_path,
                storage_provider=StorageProvider.LOCAL,
                storage_url=storage_url,
                metadata=metadata,
                description=upload_request.description,
                alt_text=upload_request.alt_text,
                is_public=upload_request.is_public,
                is_downloadable=upload_request.is_downloadable,
                status=FileStatus.READY,
                uploaded_by=user_id
            )
            
            db.add(file_record)
            await db.commit()
            await db.refresh(file_record)
            
            # Ajouter au dossier si spécifié
            if upload_request.folder_id:
                await self.add_file_to_folder(file_record.id, upload_request.folder_id, user_id, db)
            
            # Enregistrer l'activité
            await self._log_activity(file_record.id, user_id, "upload", db)
            
            return await self._file_to_response(file_record, db)
            
        except FileValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            # Nettoyer le fichier en cas d'erreur
            if 'file_path' in locals():
                await self.storage.delete_file(file_path)
            raise HTTPException(status_code=500, detail=f"Erreur upload: {str(e)}")
    
    async def get_file(self, file_id: str, user_id: str, db: AsyncSession) -> Optional[FileResponse]:
        """Récupère un fichier par ID"""
        
        query = select(FileShare).where(FileShare.id == file_id)
        result = await db.execute(query)
        file_record = result.scalar_one_or_none()
        
        if not file_record:
            return None
        
        # Vérifier les permissions
        if not await self._check_file_permission(file_record, user_id, "view", db):
            raise HTTPException(status_code=403, detail="Accès refusé")
        
        # Mettre à jour les statistiques
        file_record.view_count += 1
        file_record.last_accessed = datetime.now()
        await db.commit()
        
        # Enregistrer l'activité
        await self._log_activity(file_id, user_id, "view", db)
        
        return await self._file_to_response(file_record, db)
    
    async def update_file(
        self,
        file_id: str,
        file_update: FileUpdate,
        user_id: str,
        db: AsyncSession
    ) -> Optional[FileResponse]:
        """Met à jour les métadonnées d'un fichier"""
        
        query = select(FileShare).where(FileShare.id == file_id)
        result = await db.execute(query)
        file_record = result.scalar_one_or_none()
        
        if not file_record:
            return None
        
        # Vérifier les permissions
        if not await self._check_file_permission(file_record, user_id, "edit", db):
            raise HTTPException(status_code=403, detail="Accès refusé")
        
        # Mettre à jour les champs
        update_data = file_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(file_record, field, value)
        
        file_record.updated_at = datetime.now()
        await db.commit()
        
        # Enregistrer l'activité
        await self._log_activity(file_id, user_id, "edit", db)
        
        return await self._file_to_response(file_record, db)
    
    async def delete_file(self, file_id: str, user_id: str, db: AsyncSession) -> bool:
        """Supprime un fichier"""
        
        query = select(FileShare).where(FileShare.id == file_id)
        result = await db.execute(query)
        file_record = result.scalar_one_or_none()
        
        if not file_record:
            return False
        
        # Vérifier les permissions
        if not await self._check_file_permission(file_record, user_id, "delete", db):
            raise HTTPException(status_code=403, detail="Accès refusé")
        
        # Supprimer le fichier du disque
        await self.storage.delete_file(file_record.file_path)
        
        # Marquer comme supprimé
        file_record.status = FileStatus.DELETED
        await db.commit()
        
        # Enregistrer l'activité
        await self._log_activity(file_id, user_id, "delete", db)
        
        return True
    
    async def search_files(
        self,
        search_params: FileSearchParams,
        user_id: str,
        page: int = 1,
        per_page: int = 20,
        db: AsyncSession = None
    ) -> Dict[str, Any]:
        """Recherche des fichiers avec filtres"""
        
        query = select(FileShare).where(
            and_(
                FileShare.status == FileStatus.READY,
                or_(
                    FileShare.uploaded_by == user_id,
                    FileShare.is_public == True
                )
            )
        )
        
        # Appliquer les filtres
        if search_params.query:
            query = query.where(
                or_(
                    FileShare.original_name.ilike(f"%{search_params.query}%"),
                    FileShare.description.ilike(f"%{search_params.query}%")
                )
            )
        
        if search_params.file_type:
            query = query.where(FileShare.file_type == search_params.file_type)
        
        if search_params.mime_type:
            query = query.where(FileShare.mime_type == search_params.mime_type)
        
        if search_params.uploaded_by:
            query = query.where(FileShare.uploaded_by == search_params.uploaded_by)
        
        if search_params.min_size:
            query = query.where(FileShare.file_size >= search_params.min_size)
        
        if search_params.max_size:
            query = query.where(FileShare.file_size <= search_params.max_size)
        
        if search_params.uploaded_after:
            query = query.where(FileShare.created_at >= search_params.uploaded_after)
        
        if search_params.uploaded_before:
            query = query.where(FileShare.created_at <= search_params.uploaded_before)
        
        # Pagination
        total_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(total_query)
        total = total_result.scalar()
        
        offset = (page - 1) * per_page
        paginated_query = query.offset(offset).limit(per_page).order_by(FileShare.created_at.desc())
        
        result = await db.execute(paginated_query)
        files = result.scalars().all()
        
        # Convertir en réponses
        file_responses = []
        for file_record in files:
            file_responses.append(await self._file_to_response(file_record, db))
        
        return {
            'files': file_responses,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        }
    
    async def create_folder(
        self,
        name: str,
        user_id: str,
        parent_id: Optional[str] = None,
        db: AsyncSession = None
    ) -> FolderResponse:
        """Crée un nouveau dossier"""
        
        # Construire le chemin
        path = name
        level = 0
        
        if parent_id:
            parent_query = select(FileFolder).where(FileFolder.id == parent_id)
            parent_result = await db.execute(parent_query)
            parent_folder = parent_result.scalar_one_or_none()
            
            if not parent_folder:
                raise HTTPException(status_code=404, detail="Dossier parent non trouvé")
            
            if parent_folder.owner_id != user_id:
                raise HTTPException(status_code=403, detail="Accès refusé")
            
            path = f"{parent_folder.path}/{name}"
            level = parent_folder.level + 1
        
        # Créer le dossier
        folder = FileFolder(
            name=name,
            parent_id=parent_id,
            path=path,
            level=level,
            owner_id=user_id
        )
        
        db.add(folder)
        await db.commit()
        await db.refresh(folder)
        
        return await self._folder_to_response(folder, db)
    
    async def add_file_to_folder(
        self,
        file_id: str,
        folder_id: str,
        user_id: str,
        db: AsyncSession
    ) -> bool:
        """Ajoute un fichier à un dossier"""
        
        # Vérifier que le dossier existe et appartient à l'utilisateur
        folder_query = select(FileFolder).where(
            and_(
                FileFolder.id == folder_id,
                FileFolder.owner_id == user_id
            )
        )
        folder_result = await db.execute(folder_query)
        folder = folder_result.scalar_one_or_none()
        
        if not folder:
            raise HTTPException(status_code=404, detail="Dossier non trouvé")
        
        # Vérifier que le fichier existe
        file_query = select(FileShare).where(FileShare.id == file_id)
        file_result = await db.execute(file_query)
        file_record = file_result.scalar_one_or_none()
        
        if not file_record:
            raise HTTPException(status_code=404, detail="Fichier non trouvé")
        
        # Vérifier les permissions
        if not await self._check_file_permission(file_record, user_id, "edit", db):
            raise HTTPException(status_code=403, detail="Accès refusé")
        
        # Créer l'association
        folder_item = FileFolderItem(
            folder_id=folder_id,
            file_id=file_id
        )
        
        db.add(folder_item)
        await db.commit()
        
        return True
    
    async def _check_file_permission(
        self,
        file_record: FileShare,
        user_id: str,
        permission: str,
        db: AsyncSession
    ) -> bool:
        """Vérifie les permissions d'un utilisateur sur un fichier"""
        
        # Le propriétaire a tous les droits
        if str(file_record.uploaded_by) == user_id:
            return True
        
        # Les fichiers publics peuvent être vus et téléchargés
        if file_record.is_public and permission in ['view', 'download']:
            return True
        
        # Vérifier les permissions explicites
        permission_query = select(FilePermission).where(
            and_(
                FilePermission.file_id == file_record.id,
                FilePermission.user_id == user_id,
                or_(
                    FilePermission.expires_at.is_(None),
                    FilePermission.expires_at > datetime.now()
                )
            )
        )
        
        result = await db.execute(permission_query)
        file_permission = result.scalar_one_or_none()
        
        if not file_permission:
            return False
        
        # Vérifier la permission spécifique
        permission_map = {
            'view': file_permission.can_view,
            'download': file_permission.can_download,
            'edit': file_permission.can_edit,
            'delete': file_permission.can_delete,
            'share': file_permission.can_share
        }
        
        return permission_map.get(permission, False)
    
    async def _log_activity(
        self,
        file_id: str,
        user_id: str,
        action: str,
        db: AsyncSession,
        details: Dict[str, Any] = None
    ) -> None:
        """Enregistre une activité sur un fichier"""
        
        activity = FileActivity(
            file_id=file_id,
            user_id=user_id,
            action=action,
            details=details or {}
        )
        
        db.add(activity)
        await db.commit()
    
    async def _file_to_response(self, file_record: FileShare, db: AsyncSession) -> FileResponse:
        """Convertit un enregistrement de fichier en réponse"""
        
        # Récupérer le nom de l'uploader
        user_query = select(User.full_name).where(User.id == file_record.uploaded_by)
        user_result = await db.execute(user_query)
        uploader_name = user_result.scalar_one_or_none() or "Utilisateur inconnu"
        
        return FileResponse(
            id=file_record.id,
            original_name=file_record.original_name,
            filename=file_record.filename,
            mime_type=file_record.mime_type,
            file_type=file_record.file_type,
            file_size=file_record.file_size,
            file_path=file_record.file_path,
            storage_provider=file_record.storage_provider,
            storage_url=file_record.storage_url,
            metadata=file_record.metadata,
            description=file_record.description,
            alt_text=file_record.alt_text,
            is_public=file_record.is_public,
            is_downloadable=file_record.is_downloadable,
            status=file_record.status,
            processing_progress=file_record.processing_progress,
            download_count=file_record.download_count,
            view_count=file_record.view_count,
            created_at=file_record.created_at,
            updated_at=file_record.updated_at,
            last_accessed=file_record.last_accessed,
            uploaded_by=file_record.uploaded_by,
            uploader_name=uploader_name,
            expires_at=file_record.expires_at
        )
    
    async def _folder_to_response(self, folder: FileFolder, db: AsyncSession) -> FolderResponse:
        """Convertit un dossier en réponse"""
        
        # Récupérer le nom du propriétaire
        user_query = select(User.full_name).where(User.id == folder.owner_id)
        user_result = await db.execute(user_query)
        owner_name = user_result.scalar_one_or_none() or "Utilisateur inconnu"
        
        return FolderResponse(
            id=folder.id,
            name=folder.name,
            description=folder.description,
            color=folder.color,
            is_shared=folder.is_shared,
            parent_id=folder.parent_id,
            path=folder.path,
            level=folder.level,
            created_at=folder.created_at,
            updated_at=folder.updated_at,
            owner_id=folder.owner_id,
            owner_name=owner_name
        )


# Instance globale du service
file_service = FileService()