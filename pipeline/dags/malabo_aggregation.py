def aggregate_malabo_indicators(**context):
    """Aggregates raw data to compute Malabo indicators."""
    logger.info("📊 Starting Malabo indicator aggregation...")
    
    engine = create_engine(DATABASE_URL)
    
    try:
        # Calculate yield (production / area harvested) - this is a simplified example
        # A more accurate calculation would require area harvested data.
        query = """
            SELECT 
                country_name, 
                crop_name, 
                year, 
                AVG(value) as production_tonnes
            FROM staging_production
            WHERE unit = 'tonnes'
            GROUP BY country_name, crop_name, year
            ORDER BY year, country_name, crop_name;
        """
        df_yield = pd.read_sql(query, engine)
        
        # In a real scenario, we would also need area harvested data to calculate yield.
        # For now, we'll just save the aggregated production data.
        df_yield.to_sql('malabo_yield_indicators', engine, if_exists='replace', index=False)
        
        logger.info(f"  ✅ Successfully aggregated and saved {len(df_yield)} yield indicator records.")
        
    except Exception as e:
        logger.error(f"  ❌ Error aggregating Malabo indicators: {e}", exc_info=True)
        raise

    return True
