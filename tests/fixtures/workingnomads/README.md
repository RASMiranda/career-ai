# Working Nomads fixture (hand-trimmed, NOT a recorded response)

`exposed_jobs.json` has the field names the owner confirmed from a real response
(a JSON array; fields `url`, `title`, `description`, `company_name`, `category_name`,
`tags` as a comma string, `location`, `pub_date` as ISO 8601 with offset). The job
rows are hand-trimmed and their values are invented for the tests. Replace the file
with a recorded response (values trimmed, keys unchanged) when one is available.

It is used only by `tests/test_workingnomads.py`. Nothing here is fetched at test time.
