import tabula
pdf_path = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent_db/papers/paper1.pdf"
dfs = tabula.read_pdf(pdf_path, stream=True)
# read_pdf returns list of DataFrames
print(len(dfs))
dfs[0]