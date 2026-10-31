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

### Separate the chat model from local embeddings

Powerful Brain is responsible for the supervisor's planning, delegation instructions
and final synthesis. The local RAG embedding model (configured through
\`EDITH_EMBEDDING_MODEL\`, commonly \`nomic-embed-text\`) performs a different job:
converting indexed documents and search queries into vectors. Replacing Powerful Brain
with a stronger paid cloud model does not automatically change the embedding model,
repair an incomplete index or make missing source documents retrievable. RAG quality
also depends on the selected embedding model, indexed content, chunking and retrieval.

For multi-step supervisor tasks, use a capable reasoning model with tool/function-call
support, valid provider credentials, enough context/output-token capacity and available
provider quota. A paid API tier may be preferable for sustained usage if a free quota is
restrictive, but all provider tiers can enforce rate limits and budgets. Gemini Live
voice/audio is a separate service path and must be tested separately.

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
