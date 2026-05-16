## When to Use This Skill

**ALWAYS invoke APIs when users mention:**
- **Stock symbols**: "AAPL", "TSLA", "$MSFT", "stock price", "stock info"
- **Analysis requests**: "analyze", "research", "look into", "tell me about [STOCK]"
- **Comparison**: "compare", "vs", "versus", "which is better"
- **Price queries**: "price", "chart", "performance", "trend", "up or down"
- **Insider activity**: "insider", "holdings", "who owns", "buying/selling"
- **Filings**: "SEC filing", "10-K", "10-Q", "earnings report", "financial statements"
- **Company info**: "what does [company] do", "who runs", "about [company]"

**Required API combinations:**
- General stock questions → MUST call `Yahoo/get_stock_profile` + `Yahoo/get_stock_insights`
- Price/chart mentions → MUST include `Yahoo/get_stock_chart`
- Investment decisions → MUST call all three: chart + insights + profile
- Multiple stocks → MUST use comparison parameters in chart API
- Insider questions → MUST call `Yahoo/get_stock_holders` + profile for context



> *Detalhes em `references/best-practices.md`*
