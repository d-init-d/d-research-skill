# Specialized Data Sources

This guide covers specialized data sources organized by domain, with API endpoints, access patterns, and workflow recommendations for comprehensive research tasks.

## Financial and Market Data

### Free Sources

**Yahoo Finance (yfinance Python library)**
```
pip install yfinance
```
```python
import yfinance as yf
stock = yf.Ticker("AAPL")
hist = stock.history(period="1y")
info = stock.info
financials = stock.financials
balance_sheet = stock.balance_sheet
```

**Alpha Vantage (Free API - 5 requests/minute, 500/day)**
```
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=AAPL&apikey=YOUR_KEY
```
Register: https://www.alphavantage.co/support/#api-key
Functions: TIME_SERIES_* (daily/weekly/monthly), SYMBOL_SEARCH, NEWS_SENTIMENT, FX_DAILY

**FRED - Federal Reserve Economic Data**
```
https://api.stlouisfed.org/fred/series/observations?series_id=GDP&api_key=YOUR_KEY&file_type=json
```
Categories: GDP, CPI, unemployment, interest rates, consumer sentiment
Base: https://fred.stlouisfed.org

**World Bank API**
```
https://api.worldbank.org/v2/country/US/indicator/NY.GDP.MKTP.CD?format=json&per_page=100
```
Indicators: NY.GDP.MKTP.CD (GDP), SP.POP.TOTL (population), SL.UEM.TOTL.ZS (unemployment)

**IMF Data API**
```
https://datahelp.imf.org/developers/apis/rec/fiscal/FPP/US/A
```
Base: https://datahelp.imf.org
Tools: Data API, IFS (International Financial Statistics), Direction of Trade

**SEC EDGAR - Full-Text Search**
```
https://efts.sec.gov/LATEST/search-index?q=apple+10-K&dateRange=custom&startdt=2023-01-01&enddt=2024-01-01
```
Filings: 10-K (annual), 10-Q (quarterly), 8-K (current events), DEF 14A (proxy)
```python
# EDGAR company submissions
import requests
cik = "0000320193"  # Apple CIK
url = f"https://data.sec.gov/submissions/CIK{cik}.json"
```

### Workflow Recommendations

**Company Research**
1. Extract 10-K/10-Q filings from EDGAR for business overview, risk factors, financials
2. Pull stock price history and key metrics via yfinance
3. Get analyst recommendations and news sentiment from Alpha Vantage
4. Cross-reference with news articles for recent developments

**Market Analysis**
1. Download daily OHLCV time series (yfinance or Alpha Vantage)
2. Calculate technical indicators (pandas with TA-Lib or manual calculation)
3. Compare sector performance with index data
4. Check macroeconomic context via FRED indicators

**Macroeconomic Research**
1. World Bank for long-term GDP, development indicators across countries
2. FRED for US-specific indicators with frequent updates
3. IMF for international monetary data, exchange rates, trade statistics
4. Combine for cross-country comparisons or global economic analysis

---

## Patent and IP Data

**Google Patents**
```
https://patents.google.com/?q=machine+learning&country=US&start=0
```
Extract via HTML scraping or Google Patents Public Data (BigQuery dataset)

**USPTO PatentsView**
```
https://api.patentsview.org/patents.json?grant_date=[20230101 TO 20231231]&q=neural+network
```
Filters: patent_number, grant_date, inventor, assignee, cpc_section
Fields: patstat_num, invention_title, assignee_name

**EPO Open Patent Services (OPS)**
```
https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{publication_number}/bibliographic-information
```
Authentication: https://developers.epo.org/authentication
Rate limits apply to free tier

**WIPO PCT Patent Search**
```
https://patentscope.wipo.int/search/en/search.jsf
```
Covers international PCT applications
API: https://www.wipo.int/portal/en/developers/ipc-webservices.html

**Best Practices**
- Use PatentsView for US patent analysis (most complete dataset)
- Google Patents for broad search and prior art identification
- EPO OPS for European patents and extended family information
- WIPO for international coverage and PCT applications
- Extract: title, abstract, inventors, assignees, filing date, claims, citations

---

## Legal and Regulatory

**EUR-Lex (EU Law)**
```
https://eur-lex.europa.eu/browse/list.jsf?search=&type=search&lang=en
```
API: https://eur-lex.europa.eu/content/tools/API.html
Covers: Directives, Regulations, Treaties, CJEU case law, preparatory acts

**US Congress - congress.gov API**
```
https://api.congress.gov/v3/bills?format=json&limit=20
```
Requires: API key from https://api.congress.gov
Covers: bills, amendments, nominations, treaties, roll call votes

**Court Databases (Varies by Jurisdiction)**
| Jurisdiction | Resource | API/Access |
|-------------|----------|------------|
| US Federal | PACER (paid), RECAP (free via archive) | https://www.courtlistener.com |
| UK | The National Archives | https://www.legislation.gov.uk/api |
| Canada | CanLII | https://canlii.ca |
| Australia | Australasian Legal Information Institute | https://www.austlii.edu.au |

**Government Gazettes**
| Country | Gazette | URL |
|---------|---------|-----|
| US | Federal Register | https://www.federalregister.gov/api |
| UK | The Gazette | https://www.thegazette.co.uk/api |
| EU | Official Journal | https://eur-lex.europa.eu/oj |

**Workflow for Regulatory Research**
1. Identify applicable jurisdiction and regulatory framework
2. Search primary sources (legislation, regulations) via official portals
3. Check secondary sources for interpretations, guidelines
4. Review court cases for enforcement history and interpretations
5. Track updates through RSS feeds or alert services

---

## Government and Statistics

**US Data.gov (CKAN API)**
```
https://catalog.data.gov/api/3/action/package_search?q=climate&rows=20
```
CKAN API format: `/api/3/action/{action_name}`
Actions: package_search, resource_search, organization_list

**UK data.gov.uk**
```
https://catalog.data.gov.uk/api/3/action/package_search?q=transport
```

**Eurostat API**
```
https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nama_10_gdp?geo=US&time=2022
```
Format: `/dissemination/statistics/1.0/data/{dataset_code}`
Codes: nama_10_gdp (GDP), demo_pjan (population), namq_10_gdp (quarterly GDP)

**UN Data**
```
https://data.un.org/ws/rest/data/DF_UNDAT_SNA,1.0.ALL.ar
```
SDMX REST API: https://data.un.org/ws/rest
Covers: UN Statistical Division, UNICEF, WHO, World Bank indicators

**National Statistics Agencies**
| Agency | API Endpoint |
|--------|-------------|
| US Census | https://api.census.gov/data |
| UK ONS | https://api.ons.gov.uk/v1 |
| Statistics Canada | https://statcan.gc.ca/eng/api |
| ABS (Australia) | https://api.abs.gov.au |
| Destatis (Germany) | https://www-genesis.destatis.de |

**Best Practices for Government Statistics**
- Always cite official source and dataset code
- Note revision schedules (preliminary vs. revised data)
- Check measurement definitions and methodology notes
- Account for different reporting periods (fiscal vs. calendar year)

---

## Social Media and News (Public Data Only)

**Reddit JSON API**
```
https://www.reddit.com/r/technology.json
https://www.reddit.com/r/subreddit/search.json?q=keyword
```
Returns: title, selftext, author, created_utc, score, num_comments, permalink
Rate limits: Unauthenticated requests allowed but throttled

**Hacker News Algolia API**
```
https://hn.algolia.com/api/v1/search?query=machine+learning&tags=story
```
Fields: title, url, author, points, created_at, num_comments
Users API: https://hn.algolia.com/api/v1/users/{username}

**News API**
```
https://newsapi.org/v2/everything?q=climate+change&sortBy=relevancy&apiKey=YOUR_KEY
```
Free tier: 100 requests/day, only from major sources
Sources endpoint: https://newsapi.org/v2/top-headlines

**GDELT Project**
```
http://api.gdeltproject.org/api/2/search/keywordsearch?query=protests&mode=artlist&maxrecords=250
```
Updates: Every 15 minutes
GKG API: For geocode, themes, people, organizations in news

**Wayback Machine (CDX API)**
```
http://web.archive.org/cdx/search/cdx?url=example.com&output=text&limit=100
```
Returns: timestamp, original, mimetype, statuscode, digest

**Important Limitations**
- Twitter/X API: Requires paid access ($100+/month minimum) for meaningful data
- Social media APIs often have strict rate limits for unauthenticated requests
- Consider terms of service for commercial use
- Archive services useful for historical data and deleted content

---

## Geospatial Data

**OpenStreetMap Overpass API**
```
https://overpass-api.de/api/interpreter
```
```overpassql
[out:json][timeout:25];
area["name"="California"]->.searchArea;
node["amenity"="hospital"](area.searchArea);
out;
```
Extract: buildings, roads, amenities, boundaries, land use
Alternative: https://overpass.kumi.systems (free public instance)

**Natural Earth Data**
```
https://www.naturalearthdata.com/downloads/
```
Covers: 1:10m, 1:50m, 1:110m scales
Categories: Cultural (admin boundaries, cities), Physical (terrain, bathymetry, land cover)

**GADM - Administrative Boundaries**
```
https://geodata.ucdavis.edu/gadm/metadata/gadm41_usa_shp.zip
```
Covers: Country, state, district levels with names in multiple languages
Formats: Shapefile, GeoPackage, R (spatial) formats

**National Geoportals**
| Country | Portal | API/Format |
|---------|--------|------------|
| US | GeoPlatform | https://www.geoplatform.gov/api |
| EU | INSPIRE Geoportal | https://inspire-geoportal.ec.europa.eu |
| UK | OS Data Hub | https://osdatahub.os.uk |
| Canada | GeoGratis | https://geogratis.gc.ca/api |

**Geospatial Data Workflow**
1. Identify required coverage (global vs. country-specific)
2. Check resolution requirements (natural earth for small scale, OSM for detail)
3. Use Overpass API for dynamic OSM data with custom queries
4. Download static datasets for offline processing or complex analysis
5. Process with GDAL/OGR, GeoPandas, or PostGIS for transformations

---

## General Research Tips

1. **Check data freshness**: Note last updated dates and revision schedules
2. **Preserve provenance**: Record source URLs, API endpoints, query parameters used
3. **Handle rate limits**: Implement exponential backoff, cache responses
4. **Respect terms**: Verify permitted uses before commercial application
5. **Document methodology**: Note any cleaning, filtering, or transformation applied
6. **Multiple sources**: Cross-validate critical findings with independent sources
