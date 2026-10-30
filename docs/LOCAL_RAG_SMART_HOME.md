# EDITH local RAG, supervisor and smart-home setup

## Local knowledge base

Install the Python dependencies from \`requirements.txt\`, install Ollama, then pull a local embedding model:

\`\`\`bash
ollama pull nomic-embed-text
\`\`\`

EDITH stores vectors under \`memory/vector_db\` by default. Override the store with
\`EDITH_VECTOR_DB\`; override the local Ollama endpoint/model with
\`EDITH_EMBEDDING_URL\` and \`EDITH_EMBEDDING_MODEL\`. Text, Markdown, source files,
CSV, JSON, PDF and DOCX files can be indexed. Cloud model credentials are not used
for embedding.

Use the \`knowledge_base\` tool with \`index_file\`, \`search\` or \`stats\`. The
\`agent_supervisor\` tool uses LangGraph to retrieve local context, delegate bounded
planner/researcher/developer/security tasks through Powerful Brain, and synthesize
the results.

## Authenticated smart-home integration

Create a long-lived access token in the user's own Home Assistant profile, then run:

\`\`\`bash
python scripts/configure_home_assistant.py
\`\`\`

The URL is stored in the local EDITH config and the token is stored through EDITH's
OS keychain helper when available. If the OS keychain is unavailable, EDITH reports
that it used its legacy local-config fallback; secure the config file and migrate
the token to an OS keychain as soon as one is available. Alternatively configure \`EDITH_HOME_ASSISTANT_URL\` and
\`EDITH_HOME_ASSISTANT_TOKEN\` as environment variables.

EDITH can list entities and read states. Write actions are restricted to the
service allowlist in \`agents/smart_network.py\` and must pass the local confirmation
dialog. Pairing alone does not authorize arbitrary shell commands, raw HTTP, or
control of unrelated network hosts.
