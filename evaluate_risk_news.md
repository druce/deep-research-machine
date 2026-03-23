# Risks Section Evaluation Rubric

Score each dimension 1-10. Be harsh — a 7 is good, an 8 is excellent, a 9-10 is exceptional. Most professional equity research scores 5-7. Return JSON only.

## Dimensions

### 1. Completeness (does it cover every required element?)
Check for presence and depth of each element. For each missing or shallow element, deduct 1 point from 10:
- [ ] Recent corporate developments and their significance — with specific dates, figures, and why each matters
- [ ] Regulatory actions, legal proceedings, and compliance risks — specific cases, agencies, potential financial impact
- [ ] Strategic partnerships, M&A activity, and competitive dynamics — named counterparties, deal terms, strategic rationale
- [ ] Analyst sentiment shifts and institutional ownership changes — specific rating changes, notable position changes
- [ ] Key risk factors by category: operational risks (execution, technology, supply chain)
- [ ] Key risk factors by category: financial risks (leverage, currency, liquidity, capital allocation)
- [ ] Key risk factors by category: regulatory risks (antitrust, export controls, data privacy, sanctions)
- [ ] Key risk factors by category: market risks (cyclicality, macro sensitivity, competitive disruption)
- [ ] Source triangulation: claims confirmed by 2+ sources stated with confidence; single-source claims qualified with attribution; conflicting sources acknowledged with weighting rationale
- [ ] Missing analysis: are there significant risk topics covered in source material (SEC filings, 8-K summaries, research findings, news) that are absent from the draft? Deduct for major omissions.

Score: 10 = all 10 elements present with specific data (dates, dollar amounts, named entities), no major source topics omitted. 7 = all present but some lack specifics. 5 = 3+ elements missing or generic. 3 = mostly boilerplate.

### 2. Correct length
Count the words. Target: 2000-2800 words.
- 10 = 2000-2800 words
- 8 = 1700-2000 or 2800-3100
- 5 = 1300-1700 or 3100-3500
- 3 = under 1300 or over 3500
- 1 = under 900 or over 4000

### 3. Insight quality
- Does it explain *why* each risk matters for the investment case, not just list risks?
- Does it analyze: probability and magnitude of each risk, mitigating factors, how the market is pricing each risk, what catalysts could crystallize latent risks?
- Are risks prioritized by materiality (impact on earnings, valuation, or competitive position) rather than presented as a flat list?
- Does it distinguish between well-known risks already priced in vs. underappreciated risks the market may be ignoring?
- Are factual claims grounded in sources? Deduct for unsupported claims or speculation not traceable to indexed sources or structured artifacts.
- Are opinions clearly distinguished from facts? Analysis should use framing like "this suggests/indicates/implies" rather than presenting interpretations as objective data.
- Deduct points for: paragraphs that only restate risks without analysis, generic risk language that could apply to any company, missing "so what?" on risk factors, claims that appear fabricated or unverifiable

Score: 10 = every risk has probability/magnitude assessment with source grounding and investment implication. 7 = mostly analytical with some flat spots. 5 = half risk listing, half analysis. 3 = reads like a 10-K risk factors section with no interpretation.

### 4. Relevance
- Would a portfolio manager skip any paragraph? If yes, deduct points.
- Is there any filler, throat-clearing, or generic risk commentary that doesn't serve the investment case?
- Does it prioritize material risks (things that could move the stock 10%+) over routine business risks?
- Is there any repetition — the same risk point made in different words across paragraphs or subsections? Deduct for each instance.
- Are risks from different categories (regulatory, operational, etc.) clearly separated without overlap?
- Deduct 1 point for each paragraph that doesn't directly serve an investment decision

Score: 10 = zero filler or repetition, every sentence earns its place. 7 = tight but 1-2 soft spots. 5 = noticeable padding. 3 = half the content is skippable.

### 5. Professional style
- Reads like a Goldman/Morgan Stanley initiation, not a blog post or press release?
- Be an analyst, not a reporter — when presenting a risk, explain what it means for earnings, valuation, or the thesis
- Confident, direct assertions — not hedging with "it should be noted" or "it is worth mentioning"?
- No bullet-point lists where prose is expected (tables are fine and encouraged)?
- Clean heading hierarchy (## 7. Risks, then ### subheadings)?
- Section MUST start with `## 7. Risks` as the first line
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
