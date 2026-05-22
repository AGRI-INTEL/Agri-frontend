"""
Configuration for the data pipeline
"""

# Countries to target (ISO 3166-1 alpha-2 codes)
WEST_AFRICAN_COUNTRIES_ISO2 = {
    'Benin': 'BJ',
    'Burkina Faso': 'BF',
    'Cabo Verde': 'CV',
    "Cote d'Ivoire": 'CI',
    'Gambia': 'GM',
    'Ghana': 'GH',
    'Guinea': 'GN',
    'Guinea-Bissau': 'GW',
    'Liberia': 'LR',
    'Mali': 'ML',
    'Mauritania': 'MR',
    'Niger': 'NE',
    'Nigeria': 'NG',
    'Senegal': 'SN',
    'Sierra Leone': 'SL',
    'Togo': 'TG',
}

# FAOSTAT country codes (M49 standard)
FAO_COUNTRY_CODES = {
    'BJ': 204, # Benin
    'BF': 854, # Burkina Faso
    'CI': 384, # Côte d'Ivoire
    'GH': 288, # Ghana
    'ML': 466, # Mali
    'NE': 562, # Niger
    'NG': 566, # Nigeria
    'SN': 686, # Senegal
    'TG': 768, # Togo
}

# World Bank Indicators
WORLD_BANK_INDICATORS = {
    'AG.LND.AGRI.ZS': 'agricultural_land_percent',
    'AG.PRD.CREL.MT': 'cereal_production',
    'NY.GDP.MKTP.CD': 'gdp_current_usd',
    'SP.POP.TOTL': 'population_total',
    'AG.CON.FERT.ZS': 'fertilizer_consumption_percent',
    'NV.AGR.TOTL.ZS': 'agriculture_value_added_percent_gdp',
}

# OpenWeatherMap API
OPENWEATHER_CAPITALS = {
    'Abidjan': {'lat': 5.3600, 'lon': -4.0083, 'country': 'CI'},
    'Accra': {'lat': 5.6037, 'lon': -0.1870, 'country': 'GH'},
    'Lagos': {'lat': 6.5244, 'lon': 3.3792, 'country': 'NG'},
    'Dakar': {'lat': 14.7167, 'lon': -17.4677, 'country': 'SN'},
    'Bamako': {'lat': 12.6392, 'lon': -8.0029, 'country': 'ML'},
    'Ouagadougou': {'lat': 12.3714, 'lon': -1.5197, 'country': 'BF'},
    'Lome': {'lat': 6.1375, 'lon': 1.2123, 'country': 'TG'},
    'Cotonou': {'lat': 6.3654, 'lon': 2.4183, 'country': 'BJ'},
    'Niamey': {'lat': 13.5116, 'lon': 2.1254, 'country': 'NE'},
}

# FAOSTAT API endpoints
FAO_API_URLS = {
    'production_crops': 'http://www.fao.org/faostat/api/v1/en/data/QCL',
    'producer_prices': 'http://www.fao.org/faostat/api/v1/en/data/PP',
    'trade_matrix': 'http://www.fao.org/faostat/api/v1/en/data/TM',
    'fertilizers': 'http://www.fao.org/faostat/api/v1/en/data/RFN',
}
