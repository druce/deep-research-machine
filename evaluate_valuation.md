# Valuation Section Evaluation Rubric

Score each dimension 1-10. Be harsh — a 7 is good, an 8 is excellent, a 9-10 is exceptional. Most professional equity research scores 5-7. Return JSON only.

## Dimensions

### 1. Completeness (does it cover every required element?)
Check for presence and depth of each element. For each missing or shallow element, deduct 1 point from 10:
- [ ] Valuation methodologies identified: income-based (DCF with key assumptions), asset-based (book value, sum of parts), market-based (peer multiples, comps), and LBO analysis where applicable
- [ ] Key valuation inputs and metrics: growth rates, margins, discount rates, terminal value assumptions — with specific numbers
- [ ] Peer multiples comparison: current P/E, EV/EBITDA, EV/Revenue vs. named peers with specific values from key_ratios.csv
- [ ] Analyst ratings and opinions: consensus rating, price target range, recent rating changes, whether opinions are polarized or clustered
- [ ] Stock characteristics: volatility (beta), liquidity, institutional ownership, hedge fund ownership, meme stock status, macro sensitivities
- [ ] Historical valuation context: how current multiples compare to the stock's own history (premium/discount to historical averages)
- [ ] Source triangulation: claims confirmed by 2+ sources stated with confidence; single-source claims qualified with attribution; conflicting sources acknowledged with weighting rationale
- [ ] Missing analysis: are there significant valuation topics covered in source material (analyst reports, financial CSVs, research findings) that are absent from the draft? Deduct for major omissions.

Score: 10 = all 8 elements present with specific numbers, peer comps table, and analyst consensus detail, no major source topics omitted. 7 = all present but some lack specifics. 5 = 3+ elements missing or generic. 3 = mostly boilerplate.

### 2. Correct length
Count the words. Target: 1500-2200 words.
- 10 = 1500-2200 words
- 8 = 1300-1500 or 2200-2500
- 5 = 1000-1300 or 2500-2800
- 3 = under 1000 or over 2800
- 1 = under 700 or over 3200

### 3. Insight quality
- Does it explain *why* valuation levels matter for the investment case, not just state the multiples?
- Does it analyze: what justifies the current premium/discount to peers, whether the market is pricing in growth correctly, what would cause re-rating or de-rating?
- Are valuation conclusions evidenced with data (specific multiples, growth-adjusted ratios, scenario analysis) rather than asserted?
- Are numbers contextualized (vs. peers from key_ratios.csv, vs. own history, vs. growth expectations)?
- Does it connect valuation to business fundamentals (e.g., premium multiple justified by margin expansion, TAM growth, or competitive moat)?
- Are factual claims grounded in sources? Deduct for unsupported claims or speculation not traceable to indexed sources or structured artifacts.
- Are opinions clearly distinguished from facts? Analysis should use framing like "this suggests/indicates/implies" rather than presenting interpretations as objective data.
- Deduct points for: paragraphs that only restate multiples without analysis, generic valuation commentary that could apply to any stock, missing "so what?" on key metrics, claims that appear fabricated or unverifiable

Score: 10 = every valuation metric has analytical framing connecting it to the investment case with source grounding. 7 = mostly analytical with some flat spots. 5 = half data dump, half analysis. 3 = reads like a Bloomberg terminal printout with no interpretation.

### 4. Relevance
- Would a portfolio manager skip any paragraph? If yes, deduct points.
- Is there any filler, throat-clearing, or generic valuation commentary that doesn't serve the investment case?
- Does it prioritize material valuation drivers (things that move the stock) over textbook valuation theory?
- Is there any repetition — the same valuation point made in different words across paragraphs or subsections? Deduct for each instance.
- Are the same multiples or numbers repeated across subsections? Deduct for each instance.
- Deduct 1 point for each paragraph that doesn't directly serve an investment decision

Score: 10 = zero filler or repetition, every sentence earns its place. 7 = tight but 1-2 soft spots. 5 = noticeable padding. 3 = half the content is skippable.

### 5. Professional style
- Reads like a Goldman/Morgan Stanley initiation, not a blog post or press release?
- Be an analyst, not a reporter — when presenting a multiple, explain what it means for the stock
- Confident, direct assertions — not hedging with "it should be noted" or "it is worth mentioning"?
- No bullet-point lists where prose is expected (tables are fine and encouraged)?
- Clean heading hierarchy (## 6. Valuation, then ### subheadings)?
- Section MUST start with `## 6. Valuation` as the first line
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
