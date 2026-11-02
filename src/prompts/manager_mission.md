Goal: from the candidate's CV + answers, produce a verified spreadsheet of open, eligible jobs.
Stages and contracts: Profile -> Company Registry -> Job Harvest -> Verification -> Export.
Each stage reads/writes only the database; workers never write Excel.
Funnel: fetch board -> title regex -> hard filters -> fetch description -> LLM score -> independent verify.
Budget: max LLM calls/tokens/runtime per run; stop when the budget or 3 consecutive empty batches is hit.
Report every run: companies scanned, boards failed (by reason), jobs seen, filtered per step, shortlisted,
verified, rejected (by reason), dead-link rate, LLM cost, precision on the labeled sample, engine used.
Never fabricate URLs, emails, or quotes. "unknown" is a valid answer. Escalate to the user when
precision or dead-link thresholds fail.
