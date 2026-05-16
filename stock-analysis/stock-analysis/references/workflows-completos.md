<!-- Conteudo extraido de stock-analysis/SKILL.md via progressive-disclosure -->

## Common Workflows

### 1. Company Overview → Deep Dive
```
User: "Tell me about AAPL"
→ Yahoo/get_stock_profile (business summary, industry, employees)
→ Yahoo/get_stock_insights (technical outlook, valuation, ratings)
→ Yahoo/get_stock_chart (recent price performance)
```

### 2. Technical Analysis → Fundamental Check
```
User: "Is TSLA a good buy?"
→ Yahoo/get_stock_chart (price trends, support/resistance)
→ Yahoo/get_stock_insights (technical outlook, target price, rating)
→ Yahoo/get_stock_profile (verify business fundamentals)
```

### 3. Insider Activity Analysis
```
User: "Show me insider trading for NVDA"
→ Yahoo/get_stock_holders (insider transactions)
→ Yahoo/get_stock_profile (context about executives)
→ Yahoo/get_stock_insights (check if aligned with outlook)
```

### 4. Due Diligence Package
```
User: "Full analysis of MSFT"
→ Yahoo/get_stock_profile (company background)
→ Yahoo/get_stock_insights (analyst ratings, valuation)
→ Yahoo/get_stock_chart (historical performance)
→ Yahoo/get_stock_holders (insider sentiment)
→ Yahoo/get_stock_sec_filing (recent regulatory filings)
```

### 5. Multi-Stock Comparison
```
User: "Compare AAPL vs MSFT vs GOOGL"
→ Yahoo/get_stock_chart (with comparisons parameter)
→ Yahoo/get_stock_insights (for each symbol)
→ Compare metrics side-by-side
```

### 6. Sector Research
```
User: "Analyze tech stocks: AAPL, NVDA, AMD"
→ Yahoo/get_stock_profile (each company's focus area)
→ Yahoo/get_stock_insights (sector comparison scores)
→ Yahoo/get_stock_chart (relative performance)
```
