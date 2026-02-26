"""
src/llm/prompts.py
All prompt templates. Keep LLM instructions separate from logic.
"""

DOMAIN_CLASSIFICATION_PROMPT = """
You are a job domain classifier.

Given the following job role: "{role}"

Classify it into exactly ONE of these allowed domains:
Software Development, Data Science, Artificial Intelligence (AI), Machine Learning,
Cloud Computing, Cyber Security, Information Technology, Engineering, Design,
Digital Marketing, Marketing, Sales, Finance, Human Resources (HR), Operations,
Product Management, Project Management, Business Development, General Management,
Customer Service, Supply Chain Management (SCM), Law, Teaching, Content Writing

Respond with ONLY the domain name, nothing else.
"""

RESUME_SUMMARY_PROMPT = """
You are an expert resume summarizer for job applications.

Given the following resume, produce a concise summary (max 400 words) covering:
- Name and contact info (if present)
- Key skills (top 10)
- Education (degree, institution, year)
- Work / internship experience (role, company, duration, key achievements)
- Projects (name, tech stack, outcome)
- Certifications or achievements

Be factual. Do not invent information.

RESUME:
{resume}

Respond with the summary only, no preamble.
"""

JOB_FILTER_PROMPT = """
You are a job relevance evaluator. Evaluate the following jobs against the user's preferences.

USER PREFERENCES:
{preferences}

JOBS (JSON):
{jobs_json}

Return a JSON array of ONLY the links of jobs that are a good match.
If no jobs match, return an empty array: []

Rules:
- Match based on role, experience level, location/remote preference, and salary.
- Be inclusive when in doubt — it is better to include borderline matches.
- Return ONLY valid JSON. No explanation, no markdown, no code blocks.

Example output: ["https://example.com/job1", "https://example.com/job2"]
"""

APPLICATION_ANSWER_PROMPT = """
You are an AI assistant helping a job applicant fill out application forms.

RESUME SUMMARY:
{resume_summary}

JOB DETAILS:
Title: {job_title}
Company: {company}
Description: {description}

USER PREFERENCES:
{preferences_md}

APPLICATION QUESTIONS:
{questions_json}

For each question, provide the best possible answer based on the resume and preferences.
Return a JSON array in the SAME ORDER as the questions, where each element is an object:
{{
  "question_id": <id from input>,
  "answer": "<your answer>"
}}

Rules:
- For text questions: write a complete, professional answer (1-3 sentences unless more is needed).
- For radio/select: return exactly one of the provided options.
- For checkbox: return a list of applicable options.
- For availability: assume that you are immidiatly available to join unless specified.
- Be honest — do not fabricate experience not in the resume.
- Return ONLY valid JSON. No markdown, no explanation.
"""

STRICT_JSON_RETRY_PROMPT = """
Your previous response was not valid JSON. 

Task: {original_task}

You MUST respond with ONLY valid JSON matching this schema: {schema_description}

No markdown code blocks, no explanation, no preamble. Start your response with [ or {{.
"""
