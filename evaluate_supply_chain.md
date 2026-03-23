# Supply Chain Positioning Section Evaluation Rubric

Score each dimension 1-10. Be harsh — a 7 is good, an 8 is excellent, a 9-10 is exceptional. Most professional equity research scores 5-7. Return JSON only.

## Dimensions

### 1. Completeness (does it cover every required element?)
Check for presence and depth of each element. For each missing or shallow element, deduct 1 point from 10:
- [ ] Company's role in the upstream (supplier-side) and downstream (customer/distribution) value chain
- [ ] Key suppliers, manufacturing partners, and input dependencies (raw materials, components)
- [ ] Supplier concentration risk — single-source or limited-source dependencies identified and quantified
- [ ] Geographic exposure of the supply chain: countries, regions, trade route risks, tariff and sanctions exposure
- [ ] Logistics and distribution infrastructure, inventory management approach, and working capital implications
- [ ] Recent supply chain disruptions, changes, or vertical integration decisions
- [ ] Downstream distribution channels and customer concentration risks
- [ ] Source triangulation: claims confirmed by 2+ sources stated with confidence; single-source claims qualified with attribution; conflicting sources acknowledged with weighting rationale
- [ ] Missing analysis: are there significant supply chain topics covered in source material (SEC filings, research findings, indexed chunks) that are absent from the draft? Deduct for major omissions.

Score: 10 = all 9 elements present with specific data (named suppliers, revenue concentrations, geographic breakdowns), no major source topics omitted. 7 = all present but some lack specifics. 5 = 3+ elements missing or generic. 3 = mostly boilerplate.

### 2. Correct length
Count the words. Target: 1300-2000 words.
- 10 = 1300-2000 words
- 8 = 1100-1300 or 2000-2300
- 5 = 800-1100 or 2300-2600
- 3 = under 800 or over 2600
- 1 = under 500 or over 3000

### 3. Insight quality
- Does it explain *why* supply chain dynamics matter for the investment case, not just describe the chain?
- Does it analyze risks: concentration vulnerability, geographic/geopolitical exposure, pricing power vs suppliers, vertical integration trade-offs?
- Are supply chain advantages or vulnerabilities evidenced with data (% of revenue from single suppliers, inventory days, working capital trends) rather than asserted?
- Are numbers contextualized (vs. peers, vs. history, vs. expectations)?
- Are factual claims grounded in sources? Deduct for unsupported claims or speculation not traceable to indexed sources or structured artifacts.
- Are opinions clearly distinguished from facts? Analysis should use framing like "this suggests/indicates/implies" rather than presenting interpretations as objective data.
- Deduct points for: paragraphs that only restate facts without analysis, generic supply chain descriptions that could apply to any company, missing "so what?" on supply chain data points, claims that appear fabricated or unverifiable

Score: 10 = every claim has analytical framing with risk/opportunity analysis and source grounding. 7 = mostly analytical with some flat spots. 5 = half restatement, half analysis. 3 = reads like a corporate supply chain overview.

### 4. Relevance
- Would a portfolio manager skip any paragraph? If yes, deduct points.
- Is there any filler, throat-clearing, or generic industry context that doesn't serve the investment case?
- Does it prioritize material supply chain risks (things that move the stock) over trivial operational details?
- Is there any repetition — the same supply chain point made in different words across paragraphs or subsections? Deduct for each instance.
- Deduct 1 point for each paragraph that doesn't directly serve an investment decision

Score: 10 = zero filler or repetition, every sentence earns its place. 7 = tight but 1-2 soft spots. 5 = noticeable padding. 3 = half the content is skippable.

### 5. Professional style
- Reads like a Goldman/Morgan Stanley initiation, not a blog post or press release?
- Confident, direct assertions — not hedging with "it should be noted" or "it is worth mentioning"?
- No bullet-point lists where prose is expected (tables are fine and encouraged)?
- Clean heading hierarchy (## 4. Supply Chain Positioning, then ### subheadings)?
- Section MUST start with `## 4. Supply Chain Positioning` as the first line
- No LLM tells: "In conclusion", "Overall", "It's important to note", "comprehensive", "robust"
- Deduct points for: passive voice, weasel words, unnecessary qualifiers, repetition of the same point in different words
- Number formatting: stock prices to 2 decimals ($328.47), market cap in billions with 1 decimal ($24.3B), percentages to 1 decimal (23.4%), ratios to 1 decimal (18.3x)
- Large numbers use readable form ("$34.3 billion" not "$34,300,000,000")
- Revenue labels fiscal year explicitly
- Uses specific numbers throughout, not vague qualifiers
- Acknowledges uncertainty where it exists — does not oversell or use marketing language
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
