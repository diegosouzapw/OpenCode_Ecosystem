<!-- Conteudo extraido de stock-analysis/SKILL.md via progressive-disclosure -->

## Available APIs

### Company Information
- `Yahoo/get_stock_profile` - Company profile (business, industry, executives, contact)
- `Yahoo/get_stock_insights` - Technical indicators, valuation, ratings, research reports

### Trading & Market Data
- `Yahoo/get_stock_chart` - Historical price data with customizable timeframes

### Ownership & Compliance
- `Yahoo/get_stock_holders` - Insider holdings and transactions
- `Yahoo/get_stock_sec_filing` - SEC filing history (10-K, 10-Q, 8-K, etc.)


---

## Key Parameters

### Common Parameters
- `symbol`: Stock ticker symbol (e.g., "AAPL", "TSLA")
- `region`: Market region (US, GB, JP, etc.) - default: US
- `lang`: Response language (en-US, zh-Hant-HK, etc.) - default: en-US

### Chart-Specific
- `interval`: 1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo
- `range`: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
- `comparisons`: Compare with other symbols (e.g., "^GSPC,MSFT")
- `events`: Include dividends, splits, earnings (div, split, earn)


---

## Key Data Points

### Profile Data
- Business summary and industry classification
- Employee count and executive team
- Contact information and website
- Sector and industry metrics

### Insights Data
- **Technical outlook**: Short/intermediate/long-term signals
- **Valuation**: Relative value vs sector/market
- **Key technicals**: Support, resistance, stop-loss levels
- **Ratings**: Analyst recommendations and target prices
- **Company metrics**: Innovation, hiring, sustainability scores
- **Research reports**: Analyst reports and summaries
- **Significant events**: Recent developments

### Chart Data
- OHLC (Open, High, Low, Close) prices
- Volume data
- Adjusted close prices
- 52-week high/low
- Current trading period info

### Holder Data
- Insider names and positions
- Transaction dates and descriptions
- Holdings quantity and value
- Relationship to company

### Filing Data
- Filing type (10-K, 10-Q, 8-K, etc.)
- Filing date and title
- EDGAR URLs for full documents
- Exhibits and related documents
