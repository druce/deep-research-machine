# Financial Strength Section Evaluation Rubric

Score each dimension 1-10. Be harsh — a 7 is good, an 8 is excellent, a 9-10 is exceptional. Most professional equity research scores 5-7. Return JSON only.

## Dimensions

### 1. Completeness (does it cover every required element?)
Check for presence and depth of each element. For each missing or shallow element, deduct 1 point from 10:
- [ ] Financial leverage analysis: debt levels, interest obligations, credit ratings, debt maturity profile
- [ ] Operating leverage analysis: fixed vs. variable cost structure, scalability, margin sensitivity to revenue changes
- [ ] Cash flow generation: free cash flow trends, cash conversion, operating cash flow quality
- [ ] Working capital dynamics: receivables, inventory, payables trends and efficiency
- [ ] Capital allocation strategy: dividends, buybacks, reinvestment priorities, M&A spending
- [ ] Multi-year financial trends with specific numbers from income statement, balance sheet, and cash flow statement
- [ ] Peer comparison context: margins, returns, leverage ratios vs. comparable companies
- [ ] Source triangulation: claims confirmed by 2+ sources (e.g., SEC filing AND financial artifacts) stated with confidence; single-source claims qualified with attribution; conflicting sources acknowledged with weighting rationale
- [ ] Missing analysis: are there significant financial topics covered in source material (SEC filings, financial CSVs, research findings) that are absent from the draft? Deduct for major omissions.

Score: 10 = all 9 elements present with specific numbers from financial statements and peer context, no major source topics omitted. 7 = all present but some lack specifics or peer context is thin. 5 = 3+ elements missing or generic. 3 = mostly boilerplate.

### 2. Correct length
Count the words. Target: 1500-2200 words.
- 10 = 1500-2200 words
- 8 = 1300-1500 or 2200-2500
- 5 = 1000-1300 or 2500-2800
- 3 = under 1000 or over 2800
- 1 = under 700 or over 3200

### 3. Insight quality
- Does it explain *why* financial dynamics matter for the investment case, not just present numbers?
- Does it analyze trends: margin expansion/compression drivers, cash flow sustainability, leverage trajectory, return on capital trends?
- Are financial metrics evidenced with specific data from income_statement.csv, balance_sheet.csv, cash_flow.csv, and key_ratios.csv rather than asserted?
- Are numbers contextualized (vs. peers from key_ratios.csv, vs. history, vs. expectations)?
- Does it connect financial data to business fundamentals (e.g., operating leverage to revenue mix, working capital to business model)?
- Are factual claims grounded in sources? Deduct for unsupported claims or speculation not traceable to indexed sources or structured artifacts.
- Are opinions clearly distinguished from facts? Analysis should use framing like "this suggests/indicates/implies" rather than presenting interpretations as objective data.
- Deduct points for: paragraphs that only restate financial data without analysis, generic financial commentary that could apply to any company, missing "so what?" on key metrics, claims that appear fabricated or unverifiable

Score: 10 = every financial metric has analytical framing connecting it to the investment case with source grounding. 7 = mostly analytical with some flat spots. 5 = half data dump, half analysis. 3 = reads like a financial data summary with no interpretation.

### 4. Relevance
- Would a portfolio manager skip any paragraph? If yes, deduct points.
- Is there any filler, throat-clearing, or generic financial commentary that doesn't serve the investment case?
- Does it prioritize material financial risks and strengths (things that move the stock) over routine metrics?
- Is there any repetition — the same financial point made in different words across paragraphs or subsections? Deduct for each instance.
- Are the same numbers repeated across subsections? Deduct for each instance.
- Deduct 1 point for each paragraph that doesn't directly serve an investment decision

Score: 10 = zero filler or repetition, every sentence earns its place. 7 = tight but 1-2 soft spots. 5 = noticeable padding. 3 = half the content is skippable.

### 5. Professional style
- Reads like a Goldman/Morgan Stanley initiation, not a blog post or press release?
- Be an analyst, not a reporter — when presenting a number, explain what it means for the stock
- Confident, direct assertions — not hedging with "it should be noted" or "it is worth mentioning"?
- No bullet-point lists where prose is expected (tables are fine and encouraged)?
- Clean heading hierarchy (## 5. Financial Strength, then ## subheadings)?
- Section MUST start with `## 5. Financial Strength` as the first line
- No LLM tells: "In conclusion", "Overall", "It's important to note", "comprehensive", "robust"
- Deduct points for: passive voice, weasel words, unnecessary qualifiers, repetition of the same point in different words
- Number formatting: stock prices to 2 decimals ($328.47), market cap in billions with 1 decimal ($24.3B), percentages to 1 decimal (23.4%), ratios to 1 decimal (18.3x)
- Revenue/earnings in billions or millions as appropriate ("$4.7 billion", "$312 million")
- Large numbers use readable form ("$34.3 billion" not "$34,300,000,000")
- Revenue labels fiscal year explicitly
- Uses specific numbers throughout, not vague qualifiers
- Acknowledges uncertainty where it exists — does not oversell or use marketing language
- Attribution used sparingly — once per source type is sufficient
- Data tables are well-formatted with aligned columns and clear labels

Score: 10 = indistinguishable from a top-tier analyst's writing. 7 = professional but slightly formulaic. 5 = competent but reads like AI. 3 = obviously machine-generated.

## Output format

MUST RETURN JSON ONLY, NO MARKDOWN OR CODE FENCES.

```json
{
  "completeness": N,
  "length": N,
  "insight": N,
  "relevance": N,
  "style": N,
  "total": N.N,
  "notes": "one-line summary of biggest issue"
}
```
