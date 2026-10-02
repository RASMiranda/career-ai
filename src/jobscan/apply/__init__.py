"""Optional application submission.

Design rules (do not weaken without thinking hard):

* The LLM never drives the browser. Job pages are untrusted input; a posting
  could contain instructions. Submission is deterministic code that fills a
  form from a pre-approved answers file and nothing else.
* Unknown required question -> stop and hand the job to the human. The code
  never invents an answer, never ticks a legal consent box on its own, and
  never tries to solve or bypass a CAPTCHA.
* Everything is bounded: master switch in authorization.yaml, per-day and
  per-week caps, one application per company per window, blacklist honoured.
* Every failure is logged in a structured, redacted form so it can be fed to
  an AI to improve the adapters.
"""
