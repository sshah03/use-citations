# Eval results

Scored 2026-09-22 · 34 of 34 questions run · 34 pass

An answer passes if every quote was found in its source, Claude searched for evidence that the answer might be wrong, the answer doesn't just cite the FAQ page the question came from, and (where I checked) it doesn't disagree with the official answer. [evals/README.md](README.md) explains how it all works.

What the columns mean: **cites** is how many quotes the answer has. **verified** and **failed** are how many were and weren't found in the saved documents. **warn** is things the checker flagged for a person to look at without failing the answer, such as a wrong page number or a quote that appears twice. **disconf.** is whether Claude searched for evidence against its answer. **circular** is whether it only cited the FAQ page. **agrees** is my judgment of whether it matches the official answer.

| id | domain | cites | verified | failed | warn | disconf. | circular | agrees | pass |
|---|---|---:|---:|---:|---:|:-:|:-:|:-:|:-:|
| pm-mammography | health-research | 4 | 4 | 0 | 0 | yes | no | yes | pass |
| pm-anticoag-trauma | health-research | 4 | 4 | 0 | 0 | yes | no | yes | pass |
| pm-necrotizing-hbo | health-research | 4 | 4 | 0 | 0 | yes | no | yes | pass |
| pm-acupuncture-voice | health-research | 3 | 3 | 0 | 0 | yes | no | partial | pass |
| pm-diabetes-fdgpet | health-research | 3 | 3 | 0 | 0 | yes | no | yes | pass |
| pm-aneurysm-80 | health-research | 33 | 33 | 0 | 1 | yes | no | partial | pass |
| tax-address | tax | 29 | 29 | 0 | 1 | yes | no | yes | pass |
| tax-1040x-efile | tax | 23 | 23 | 0 | 1 | yes | no | yes | pass |
| tax-dependent-age | tax | 3 | 3 | 0 | 1 | yes | no | yes | pass |
| tax-lost-refund | tax | 31 | 31 | 0 | 1 | yes | no | yes | pass |
| tax-w2-vs-1099 | tax | 37 | 37 | 0 | 0 | yes | no | yes | pass |
| tax-inherited-sale | tax | 4 | 4 | 0 | 0 | yes | no | yes | pass |
| tax-minister-housing | tax | 3 | 3 | 0 | 0 | yes | no | yes | pass |
| ip-what-protected | law-ip | 3 | 3 | 0 | 0 | yes | no | yes | pass |
| ip-register-required | law-ip | 3 | 3 | 0 | 0 | yes | no | yes | pass |
| ip-duration | law-ip | 5 | 5 | 0 | 0 | yes | no | yes | pass |
| ip-infringed | law-ip | 55 | 55 | 0 | 1 | yes | no | yes | pass |
| ip-quotes-samples | law-ip | 6 | 6 | 0 | 0 | yes | no | yes | pass |
| fin-free-credit-report | consumer-finance | 3 | 3 | 0 | 1 | yes | no | yes | pass |
| fin-pmi-removal | consumer-finance | 4 | 4 | 0 | 0 | yes | no | yes | pass |
| fin-debt-collector-calls | consumer-finance | 4 | 4 | 0 | 0 | yes | no | yes | pass |
| fin-deposit-hold | consumer-finance | 3 | 3 | 0 | 1 | yes | no | partial | pass |
| emp-weekend-night-pay | law-employment | 3 | 3 | 0 | 0 | yes | no | yes | pass |
| emp-breaks | law-employment | 3 | 3 | 0 | 0 | yes | no | yes | pass |
| emp-overtime-due | law-employment | 2 | 2 | 0 | 0 | yes | no | yes | pass |
| emp-max-hours | law-employment | 2 | 2 | 0 | 0 | yes | no | yes | pass |
| emp-pay-stubs | law-employment | 12 | 12 | 0 | 1 | yes | no | yes | pass |
| eeoc-attorney | law-employment | 3 | 3 | 0 | 0 | yes | no | yes | pass |
| eeoc-time-limit | law-employment | 2 | 2 | 0 | 0 | yes | no | yes | pass |
| eeoc-confidential | law-employment | 25 | 25 | 0 | 2 | yes | no | yes | pass |
| fda-generics-safe | health-regulation | 4 | 4 | 0 | 1 | yes | no | yes | pass |
| fda-expiration | health-regulation | 18 | 18 | 0 | 1 | yes | no | yes | pass |
| fda-generic-side-effects | health-regulation | 28 | 28 | 0 | 2 | yes | no | yes | pass |
| fda-all-generics | health-regulation | 3 | 3 | 0 | 1 | yes | no | yes | pass |

Altogether: 372 of 372 quotes found, 0 not found. 34 of 34 answers searched for evidence against themselves, and 0 only cited the FAQ page.

## Notes

For each answer I checked by hand: what the official answer says, and how the skill's answer compares.

- **pm-mammography**: PubMedQA label 'yes'. Both tailored interventions raised on-schedule screening compared with usual care. The effect was strongest in year one and for women who had not been screening on schedule before.
- **pm-anticoag-trauma**: PubMedQA label 'no'. The abstract reports a 21% complication rate and calls for prospective studies. It does not conclude that the practice is safe.
- **pm-necrotizing-hbo**: PubMedQA label 'no'. The HBO (hyperbaric oxygen) group had higher mortality and more débridements. The one favourable measure was not statistically significant, and the authors 'cast doubt' on the treatment.
- **pm-acupuncture-voice**: PubMedQA label 'yes'. The study's results say vocal function and quality of life improved in both the real and the sham acupuncture groups, but not in the no-treatment group. Structural improvement (smaller lesions) appeared only with genuine acupuncture. The conclusion credits acupuncture with 'improvement in vocal function and healing of vocal fold lesions'. I judged this 'partial' because the functional gain was not specific to genuine acupuncture. The lesion-healing finding is what supports the label.
- **pm-diabetes-fdgpet**: PubMedQA label 'no'. The AUCs (a measure of diagnostic accuracy) did not differ by diabetes status (P>0.05).
- **pm-aneurysm-80**: PubMedQA reference for this abstract is 'yes'. The answer says repair is supported for selected patients over 80 (good grade, independent before the illness) and not for the age group as a whole. It cites a 2025 meta-analysis, five series and the 2023 AHA/ASA guideline (through a secondary summary). That is consistent with the reference's qualified yes. I judged it partial because the guideline itself could not be captured.
- **tax-address**: IRS Topic 157 lists four ways: Form 8822, a written statement, the new address on your return, or in person or by phone with identity verification. The answer covers all four, and adds Rev. Proc. 2010-16 and the last-known-address regulation.
- **tax-1040x-efile**: IRS: yes. You can file Form 1040-X electronically with tax software for the current and two prior tax periods. Otherwise you file on paper. The answer matches and lists the cases where the instructions require paper.
- **tax-dependent-age**: IRS FAQ: under 19, or under 24 if a full-time student. There is no age limit if the child is permanently and totally disabled.
- **tax-lost-refund**: IRS FAQ: ask for a refund trace by phone or on Form 3911. If the check was not cashed, a replacement is issued. If it was cashed, the Bureau of the Fiscal Service (BFS) sends a claim package. The answer matches, drawing on the Internal Revenue Manual (IRM) and 31 CFR 245. The FAQ page itself was flagged as a low-yield capture (the saved copy held little text) and was not cited.
- **tax-w2-vs-1099**: IRS FAQ: a W-2 reports an employee's wages and withholding. A 1099-NEC reports pay to non-employees. A 1099-MISC reports other payments. The answer matches, using the form instructions, and adds the statutory-employee case and the 2020 split between the two 1099 forms.
- **tax-inherited-sale**: IRS FAQ: the sale proceeds are not income as such. Any gain over the basis (the fair market value at the date of death) may be a taxable capital gain.
- **tax-minister-housing**: IRS FAQ: the allowance is excluded from gross income for income tax, within limits. It is included in earnings for self-employment (SE) tax. It must be designated in advance.
- **ip-what-protected**: Copyright Office FAQ: original works of authorship in the listed categories. Ideas, systems, methods and facts are not protected.
- **ip-register-required**: Copyright Office FAQ: no. Protection exists from the moment of creation. Registration is voluntary, but you need it to sue and to claim certain remedies.
- **ip-duration**: Copyright Office FAQ: the author's life plus 70 years. For anonymous or pseudonymous works and works made for hire, 95 years from publication or 120 from creation. Works from before 1978 follow different rules.
- **ip-infringed**: Copyright Office FAQ: consult an attorney. You can bring a civil suit in federal district court. Willful infringement for profit may lead to a criminal investigation. The answer covers all three. From the same Office's pages it adds the §512 takedown route and the Copyright Claims Board (CCB), and gives the §411 registration requirement and the §412 bar as limits.
- **ip-quotes-samples**: Copyright Office FAQ: yes, you could be sued. Fair use depends on four factors, and no fixed amount of copying is automatically safe.
- **fin-free-credit-report**: Ask CFPB: you can get a free report from each nationwide credit bureau through AnnualCreditReport.com, and more free reports in specific circumstances.
- **fin-pmi-removal**: Ask CFPB: you can ask for cancellation at 80% loan-to-value (LTV). The request must be in writing, with a good payment history, payments current and no junior liens. PMI ends automatically at 78% if you are current.
- **fin-debt-collector-calls**: Ask CFPB: between 8am and 9pm unless you agree otherwise. More than seven calls in seven days, or a call within seven days of a conversation, is presumed to be harassment.
- **fin-deposit-hold**: Ask CFPB: generally by the second business day. Some funds are available the next day, and longer holds are allowed under listed exceptions. The answer gets the schedule right. The exceptions are recorded as a gap because § 229.13 was not captured.
- **emp-weekend-night-pay**: DOL FAQ: the FLSA does not require extra pay for weekend or night work as such. That's for the employer and employee to agree between themselves. Overtime applies only after 40 hours.
- **emp-breaks**: DOL FAQ: the FLSA does not require breaks. Short breaks, if given, must be paid. Bona fide meal periods of 30 minutes or more need not be. The answer matches on how breaks are treated. It states the 'not required' point as a gap because no captured text says it.
- **emp-overtime-due**: DOL FAQ: overtime is due for hours over 40 in a workweek, at 1.5 times the regular rate. There is no federal requirement for extra pay on weekends or holidays as such. The reference page could not be captured, so I judged against the text recorded when the question was pulled.
- **emp-max-hours**: DOL FAQ: the FLSA sets no limit on hours per day or per week for employees aged 16 and older. It does require overtime pay.
- **emp-pay-stubs**: DOL elaws: the FLSA requires employers to keep accurate records but does not require pay stubs. State law may. The answer matches, citing 29 U.S.C. 211(c), 29 CFR 516 and a state example.
- **eeoc-attorney**: EEOC FAQ: you do not need an attorney to file a charge.
- **eeoc-time-limit**: EEOC FAQ: 180 days. This extends to 300 days where a state or local agency enforces a law against the same discrimination.
- **eeoc-confidential**: EEOC youth FAQ: what you say is confidential until you file a charge. If you decide not to file, nothing goes to the company. Once a charge is filed, the employer is notified within ten days. The answer matches and cites 42 U.S.C. 2000e-5(b) and 29 CFR 1601.14 for the notice rule.
- **fda-generics-safe**: FDA: yes. A generic has the same active ingredient, strength, dosage form and route, and is bioequivalent (works in the body the same way). The answer cites the approval standard instead of claiming outright that generics are effective. I judged it as agreeing because the FDA's own answer rests on that standard.
- **fda-expiration**: FDA: the expiration date is the date through which the manufacturer guarantees full potency and safety under the labeled storage conditions. 21 CFR 211.137 requires it, based on stability testing. The answer matches and squares this with the SLEP extension program.
- **fda-generic-side-effects**: FDA Q&A: generics are expected to have the same safety profile, but inactive ingredients can differ and a small number of people may react differently. The answer matches, and adds the FDA's warning about some tacrolimus generics as an exception.
- **fda-all-generics**: FDA Q&A: no. Patents and exclusivity periods protect brand drugs for a time, and some drugs have no generic because no company has applied to make one.
