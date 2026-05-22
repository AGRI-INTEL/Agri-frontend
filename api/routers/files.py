"""
API endpoints pour la gestion des fichiers
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import get_db
from src.services.auth import get_current_verified_user
from src.services.files import file_service
from api.models.sql.user import User
from api.schemas.files import (
    FileResponse, FileCreate, FileUpdate, FileListResponse,
    FolderResponse, FolderCreate, FolderUpdate, FolderTreeNode,
    FileUploadRequest, FileSearchParams, FileStats,
    FilePermissionCreate, FilePermissionResponse,
    MultipleFileUploadResponse
)

router = APIRouter()


# Routes pour les fichiers

@router.post("/upload", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    alt_text: Optional[str] = Form(None),
    is_public: bool = Form(False),
    is_downloadable: bool = Form(True),
    folder_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Uploader un fichier"""
    
    upload_request = FileUploadRequest(
        description=description,
        alt_text=alt_text,
        is_public=is_public,
        is_downloadable=is_downloadable,
        folder_id=folder_id
    )
    
    return await file_service.upload_file(file, str(current_user.id), upload_request, db)


@router.post("/upload-multiple", response_model=MultipleFileUploadResponse)
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    folder_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Uploader plusieurs fichiers"""
    
    uploaded_files = []
    failed_files = []
    
    for file in files:
        try:
            upload_request = FileUploadRequest(folder_id=folder_id)
            result = await file_service.upload_file(file, str(current_user.id), upload_request, db)
            uploaded_files.append(result)
        except Exception as e:
            failed_files.append({
                'filename': file.filename,
                'error': str(e)
            })
    
    return MultipleFileUploadResponse(
        uploaded_files=uploaded_files,
        failed_files=failed_files,
        total_uploaded=len(uploaded_files),
        total_failed=len(failed_files)
    )


@router.get("/files/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Récupérer un fichier par ID"""
    
    file_data = await file_service.get_file(file_id, str(current_user.id), db)
    if not file_data:
        raise HTTPException(status_code=404, detail="Fichier non trouvé")
    
    return file_data


@router.put("/files/{file_id}", response_model=FileResponse)
async def update_file(
    file_id: str,
    file_update: FileUpdate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Mettre à jour un fichier"""
    
    file_data = await file_service.update_file(file_id, file_update, str(current_user.id), db)
    if not file_data:
        raise HTTPException(status_code=404, detail="Fichier non trouvé")
    
    return file_data


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Supprimer un fichier"""
    
    success = await file_service.delete_file(file_id, str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=404, detail="Fichier non trouvé")
    
    return {"message": "Fichier supprimé avec succès"}


@router.get("/files", response_model=FileListResponse)
async def search_files(
    query: Optional[str] = None,
    file_type: Optional[str] = None,
    mime_type: Optional[str] = None,
    folder_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Rechercher des fichiers"""
    
    search_params = FileSearchParams(
        query=query,
        file_type=file_type,
        mime_type=mime_type,
        folder_id=folder_id
    )
    
    result = await file_service.search_files(search_params, str(current_user.id), page, per_page, db)
    
    return FileListResponse(
        files=result['files'],
        total=result['total'],
        page=result['page'],
        per_page=result['per_page'],
        pages=result['pages']
    )


# Routes pour les dossiers

@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    folder_data: FolderCreate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Créer un nouveau dossier"""
    
    return await file_service.create_folder(
        folder_data.name,
        str(current_user.id),
        folder_data.parent_id,
        db
    )


@router.get("/folders/{folder_id}", response_model=FolderResponse)
async def get_folder(
    folder_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Récupérer un dossier par ID"""
    
    folder = await file_service.get_folder(folder_id, str(current_user.id), db)
    if not folder:
        raise HTTPException(status_code=404, detail="Dossier non trouvé")
    
    return folder


@router.put("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: str,
    folder_update: FolderUpdate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Mettre à jour un dossier"""
    
    folder = await file_service.update_folder(folder_id, folder_update, str(current_user.id), db)
    if not folder:
        raise HTTPException(status_code=404, detail="Dossier non trouvé")
    
    return folder


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Supprimer un dossier"""
    
    success = await file_service.delete_folder(folder_id, str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=404, detail="Dossier non trouvé")
    
    return {"message": "Dossier supprimé avec succès"}


@router.get("/folders", response_model=List[FolderTreeNode])
async def get_folder_tree(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Récupérer l'arborescence des dossiers"""
    
    return await file_service.get_folder_tree(str(current_user.id), db)


@router.post("/folders/{folder_id}/files/{file_id}")
async def add_file_to_folder(
    folder_id: str,
    file_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Ajouter un fichier à un dossier"""
    
    success = await file_service.add_file_to_folder(file_id, folder_id, str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=400, detail="Impossible d'ajouter le fichier au dossier")
    
    return {"message": "Fichier ajouté au dossier"}


@router.delete("/folders/{folder_id}/files/{file_id}")
async def remove_file_from_folder(
    folder_id: str,
    file_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Retirer un fichier d'un dossier"""
    
    success = await file_service.remove_file_from_folder(file_id, folder_id, str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=400, detail="Impossible de retirer le fichier du dossier")
    
    return {"message": "Fichier retiré du dossier"}


# Routes pour les permissions

@router.post("/files/{file_id}/permissions", response_model=FilePermissionResponse, status_code=status.HTTP_201_CREATED)
async def create_file_permission(
    file_id: str,
    permission_data: FilePermissionCreate,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Créer une permission sur un fichier"""
    
    return await file_service.create_file_permission(file_id, permission_data, str(current_user.id), db)


@router.get("/files/{file_id}/permissions", response_model=List[FilePermissionResponse])
async def get_file_permissions(
    file_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Récupérer les permissions d'un fichier"""
    
    return await file_service.get_file_permissions(file_id, str(current_user.id), db)


@router.delete("/files/{file_id}/permissions/{permission_id}")
async def delete_file_permission(
    file_id: str,
    permission_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Supprimer une permission"""
    
    success = await file_service.delete_file_permission(permission_id, str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=404, detail="Permission non trouvée")
    
    return {"message": "Permission supprimée"}


# Routes pour les statistiques

@router.get("/stats", response_model=FileStats)
async def get_file_stats(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Récupérer les statistiques des fichiers"""
    
    return await file_service.get_user_file_stats(str(current_user.id), db)