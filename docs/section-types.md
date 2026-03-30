# Document Section Types — Ground Truth Annotation Guide

## Purpose

Section types describe the **physical structure** of a financial report — where content
sits in the PDF. They do NOT describe semantic content (e.g. "this table is about PPE").
Semantic classification (DISC.PPE, DISC.REVENUE, etc.) happens later in the pipeline
via reference tracing from primary statements to notes.

## Section Types

### Primary Financial Statements

| Type | Description |
|------|-------------|
| `PNL` | Profit and loss statement / income statement |
| `SFP` | Statement of financial position / balance sheet |
| `OCI` | Other comprehensive income (IFRS only) |
| `CFS` | Cash flow statement |
| `SOCIE` | Statement of changes in equity |

### Document Structure

| Type | Description |
|------|-------------|
| `TOC` | Table of contents / Inhaltsverzeichnis. The structural overview page(s) of the document. |
| `NOTES` | Notes to the financial statements (Anhang). Includes all note disclosures — PPE schedules, tax reconciliations, segment breakdowns, etc. The pipeline later classifies individual tables within NOTES via reference tracing. |
| `FRONT_MATTER` | Cover page, table of contents, key figures at a glance, highlights, shareholder letter |
| `MANAGEMENT_REPORT` | Management commentary on business performance, outlook, risks |
| `AUDITOR_REPORT` | Independent auditor's report / opinion |
| `CORPORATE_GOVERNANCE` | Corporate governance report, board composition |
| `ESG` | Sustainability report, ESRS disclosures, non-financial statement |
| `RISK_REPORT` | Standalone risk report (banks, insurers). Distinct from risk section in management report. |
| `REMUNERATION_REPORT` | Board remuneration / compensation report (listed companies) |
| `SUPERVISORY_BOARD` | Supervisory board report (Bericht des Aufsichtsrats) |
| `RESPONSIBILITY_STATEMENT` | Directors' responsibility statement / legal representatives' declaration |
| `APPENDIX` | Standalone appendices/schedules not part of notes (e.g. UGB Anlagenspiegel presented as Beilage) |
| `OTHER` | Anything not covered above (glossary, index, contact info, etc.) |

---

## Austrian / German Term Mapping

### UGB (Unternehmensgesetzbuch) Reports

Typical structure of a UGB Jahresabschluss:

| German Term | Section Type | Notes |
|-------------|-------------|-------|
| **Deckblatt** | `FRONT_MATTER` | Cover page |
| **Inhaltsverzeichnis** | `FRONT_MATTER` | Table of contents |
| **Kennzahlen / Auf einen Blick** | `FRONT_MATTER` | Key figures summary |
| **Lagebericht** | `MANAGEMENT_REPORT` | Management report (required by UGB for large/medium companies) |
| **Konzernlagebericht** | `MANAGEMENT_REPORT` | Group management report |
| **Bilanz** | `SFP` | Balance sheet (Aktiva + Passiva) |
| **Gewinn- und Verlustrechnung** | `PNL` | Income statement (Gesamtkostenverfahren or Umsatzkostenverfahren) |
| **Kapitalflussrechnung** | `CFS` | Cash flow statement (optional for UGB single-entity, required for groups) |
| **Eigenkapitalveränderungsrechnung** | `SOCIE` | Statement of changes in equity (optional for UGB) |
| **Anhang** | `NOTES` | Notes to the financial statements |
| **Erläuterungen zur Bilanz** | `NOTES` | Balance sheet notes (subsection of Anhang) |
| **Erläuterungen zur GuV** | `NOTES` | Income statement notes (subsection of Anhang) |
| **Bilanzierungs- und Bewertungsmethoden** | `NOTES` | Accounting policies (subsection of Anhang) |
| **Sonstige Angaben** | `NOTES` | Other disclosures (subsection of Anhang) |
| **Anlagenspiegel** | `APPENDIX` | Fixed asset movement schedule — when presented as a standalone Beilage/Anlage. If embedded within Anhang, the parent section is NOTES. |
| **Entwicklung des Anlagevermögens** | `APPENDIX` | Same as Anlagenspiegel |
| **Rückstellungsspiegel** | `APPENDIX` | Provisions movement schedule (when standalone) |
| **Verbindlichkeitenspiegel** | `APPENDIX` | Liabilities maturity schedule (when standalone) |
| **Bestätigungsvermerk** | `AUDITOR_REPORT` | Auditor's report |
| **Bericht des Abschlussprüfers** | `AUDITOR_REPORT` | Auditor's report (alternative wording) |
| **Bericht des Aufsichtsrats** | `SUPERVISORY_BOARD` | Supervisory board report |
| **Erklärung der gesetzlichen Vertreter** | `RESPONSIBILITY_STATEMENT` | Legal representatives' declaration |
| **Nichtfinanzieller Bericht** | `ESG` | Non-financial statement (NaDiVeG) |
| **Nachhaltigkeitsbericht** | `ESG` | Sustainability report (ESRS/CSRD) |
| **Corporate-Governance-Bericht** | `CORPORATE_GOVERNANCE` | Governance report |
| **Vergütungsbericht** | `REMUNERATION_REPORT` | Remuneration report |

### IFRS Reports (Austrian Listed Companies)

Typical structure of an IFRS Konzernbericht / Group Annual Report:

| English Term | German Term | Section Type |
|-------------|-------------|-------------|
| Cover / Highlights | Deckblatt / Highlights | `FRONT_MATTER` |
| Contents | Inhaltsverzeichnis | `FRONT_MATTER` |
| Letter to shareholders | Brief an die Aktionäre | `FRONT_MATTER` |
| Key figures at a glance | Kennzahlen im Überblick | `FRONT_MATTER` |
| Group management report | Konzernlagebericht | `MANAGEMENT_REPORT` |
| Consolidated statement of profit or loss | Konzern-Gewinn- und Verlustrechnung | `PNL` |
| Consolidated statement of comprehensive income | Konzern-Gesamtergebnisrechnung | `OCI` |
| Consolidated statement of financial position | Konzernbilanz | `SFP` |
| Consolidated statement of changes in equity | Konzern-Eigenkapitalveränderungsrechnung | `SOCIE` |
| Consolidated statement of cash flows | Konzern-Kapitalflussrechnung | `CFS` |
| Notes to the consolidated financial statements | Konzernanhang | `NOTES` |
| Risk report | Risikobericht | `RISK_REPORT` |
| Auditor's report | Bestätigungsvermerk | `AUDITOR_REPORT` |
| Corporate governance report | Corporate-Governance-Bericht | `CORPORATE_GOVERNANCE` |
| Remuneration report | Vergütungsbericht | `REMUNERATION_REPORT` |
| Supervisory board report | Bericht des Aufsichtsrats | `SUPERVISORY_BOARD` |
| Responsibility statement | Erklärung der gesetzlichen Vertreter | `RESPONSIBILITY_STATEMENT` |
| Sustainability / ESG report | Nachhaltigkeitsbericht | `ESG` |
| Appendices | Anhänge / Beilagen | `APPENDIX` |

### Banking / Insurance Specific

| Term | Section Type | Notes |
|------|-------------|-------|
| Risikobericht | `RISK_REPORT` | Standalone risk report with detailed quantitative disclosures (Basel III/Solvency II) |
| ICAAP / ILAAP disclosures | `RISK_REPORT` | Capital/liquidity adequacy |
| Embedded Value Report | `RISK_REPORT` | Insurance-specific |

---

## Annotation Rules

1. **Tag the physical location, not the content.** If the Anlagenspiegel is inside the Anhang section, the parent section is NOTES. If it's a separate Beilage after the Anhang, it's APPENDIX.

2. **One section per structural block.** If the report has a combined "Bilanz und Gewinn- und Verlustrechnung" section, create two entries (SFP and PNL) with overlapping or adjacent page ranges.

3. **Notes are one section.** Don't split notes into DISC.PPE, DISC.TAX, etc. — that's pipeline work. Tag the entire Anhang as NOTES with start/end pages.

4. **Use FRONT_MATTER generously.** Everything before the management report or financial statements is FRONT_MATTER — cover, TOC, highlights, shareholder letter, company overview.

5. **MANAGEMENT_REPORT includes risk discussion.** Unless there's a clearly separate standalone Risikobericht section (common in banks), risk commentary within the Lagebericht stays as MANAGEMENT_REPORT.

6. **When in doubt, use OTHER.** It's better to tag a section as OTHER than to guess wrong. The annotator can always refine later.
