# Friday UGC → Mapeamento para a vaga (AI Technical Lead)

> Documento de apoio à candidatura. Cruza a descrição da função com evidências concretas no repositório FridayUGC — e indica onde reforçar narrativa pessoal (liderança, anos de experiência, P&L).

**Vaga:** entrega técnica end-to-end de casos de uso de IA · autoridade técnica no squad · standards · industrialização · cloud · RAG · agentes · MLOps/LLMOps

---

## Resumo executivo (elevator pitch)

**Friday UGC** é um caso de uso de IA **end-to-end e production-shaped**: cérebro LLM na cloud (AWS GPU + vLLM), agente móvel que opera Instagram via Accessibility API, RAG para curadoria de galeria e estilo de captions, observabilidade LLMOps (traces, métricas, eval harness), gates de segurança e deployment automatizado (Docker, CloudFormation, CI).

Demonstra capacidade de **traduzir requisito de negócio** (“operar persona UGC no Instagram de forma autónoma e segura”) em **arquitetura**, **integração** (telefone ↔ API ↔ modelo), **governação** (aprovações, budgets, sanitização) e **industrialização** (mock para CI, health checks, indexação RAG incremental).

Não substitui CV de 10+ anos ou experiência de liderar squads — complementa com **prova técnica verificável**.

---

## Descrição da função → evidência FridayUGC

| Descrição da função | O que FridayUGC demonstra | Onde ver |
|---------------------|---------------------------|----------|
| Entrega técnica **end-to-end** de casos de uso de IA | Brain + Android + infra + protocolo partilhado + content pipeline completo | `README.md`, `docs/ARCHITECTURE.md` |
| Soluções **escaláveis, robustas, prontas para produção** | Guards no servidor, idempotência, fallbacks RAG, retries LLM, CI, deploy IaC | `brain/app/agent/prompt.py`, `brain/app/retrieval/`, `infra/` |
| **Autoridade técnica** — requisitos → arquitetura | Decisão remote-brain/local-hands, abstração `LLMClient`, RAG sem over-engineering | `docs/ARCHITECTURE.md`, `docs/TECH_STACK.md` |
| **Standards, padrões, governação** | Action protocol partilhado, Pydantic schemas, safety layer, approval gates | `shared/action_protocol.md`, `docs/SAFETY_AND_BANS.md` |

**Na entrevista:** usar Friday como **referência de como você desenha e entrega** um caso de uso completo, não como único projeto da carreira.

---

## Responsabilidades → mapeamento

### 1. Definir e supervisionar arquitetura e desenho técnico

| Requisito | Evidência no projeto |
|-----------|----------------------|
| Arquitetura alinhada a requisitos | Split **brain (razão) / phone (execução)** — requisito: modelo grande na cloud, conta real no telemóvel |
| Desenho técnico documentado | `docs/ARCHITECTURE.md`, diagramas Mermaid, `docs/CASE_STUDY.md` |
| Modelo agnóstico | `brain/app/llm/` — swap mock / Ollama / vLLM / Azure sem reescrever negócio |
| Integrações | REST + Bearer token, S3 gallery, Android client, optional MAF/Azure |

**Talking point:** *“Separei concerns para escalar inferência independentemente do executor e para testar o pipeline inteiro com mock LLM em CI.”*

---

### 2. Liderar execução no squad (tarefas, priorização, qualidade)

FridayUGC é projeto **individual/portfolio** — não prova gestão de equipa. **Complementar no CV/entrevista** com:

- Exemplos reais de priorização (MVP agent loop antes de RAG; safety antes de autonomia total)
- Code review / mentoria se aplicável
- Como partiria o backlog deste produto para um squad (brain, mobile, MLOps, content)

**Estrutura de squad hipotética (mostra pensamento de lead):**

| Stream | Entregáveis |
|--------|-------------|
| Platform / MLOps | vLLM, embeddings, `/runs/metrics`, deploy |
| AI / Backend | Agent loop, RAG, UGC director, inbox |
| Mobile | Accessibility agent, sync, posting |
| Risk / Compliance | Approval gates, read-only mode, audit |

---

### 3. Escalabilidade, performance, manutenção

| Aspeto | Implementação FridayUGC |
|--------|-------------------------|
| **Escalabilidade inferência** | vLLM em GPU dedicada; brain stateless; filas SQLite → evolução para Postgres/SQS |
| **Escalabilidade RAG** | Index SQLite + top-K antes do LLM (evita context overflow); Azure embeddings ready |
| **Performance** | RAG subset na curadoria; histórico de steps no request (evita prompts de 2k+ tokens no MAF) |
| **Manutenção** | Testes pytest, eval fixtures, `.env.example`, modular `brain/app/` |

**Gap honesto:** escala multi-tenant / multi-conta ainda não implementada — arquitetura permite evolução.

---

### 4. Standards de plataforma, arquitetura de dados, integrações

| Standard | FridayUGC |
|----------|-----------|
| API contract | OpenAPI/FastAPI, schemas Pydantic |
| Observabilidade | Session traces JSON, `GET /runs/metrics` |
| Dados | Manifest S3, SQLite (queue, operator, RAG index), ledger inbox |
| Segurança | Token Bearer, sanitização copy, approval para post/comment/dm |
| CI/CD | GitHub Actions (brain + APK) |

**Integração cloud:** AWS (EC2 GPU, S3, CloudFormation) + path Azure (embeddings, MAF backend).

---

### 5. Colaborar com Business Owner e AI Factory

Traduzir **negócio → técnico** no domínio UGC:

| Negócio | Técnico |
|---------|---------|
| “Voz consistente Lorena” | Persona pack + RAG de captions posted + phrase rotation |
| “Não levar ban no IG” | Read-only default, pacing humano, approval gates |
| “Planear semana de conteúdo” | `/ugc/curate` + vision + RAG gallery |
| “Operar conta autonomamente” | Operator day-plan + agent loop + budgets |

**AI Factory angle:** componentes reutilizáveis — `LLMClient`, `retrieval/`, eval harness — aplicáveis a outros casos de uso (inbox, curadoria, agentes UI).

---

### 6. Orientar data scientists e engenheiros

Usar Friday para **ensinar padrões**:

- Porque RAG antes de fine-tuning
- Porque guards no servidor, não só no prompt
- Como escrever eval fixtures antes de produção
- Quando MAF vs loop Python simples

**Doc de onboarding técnico:** `docs/TECH_STACK.md`, `docs/SETUP_GUIDE.md`

---

### 7. Industrialização e deployment (com MLOps)

| MLOps / LLMOps | Evidência |
|----------------|-----------|
| Model serving | vLLM + Gemma 4 (`infra/docker-compose.yml`) |
| Vision pipeline | `brain/app/gallery/vision.py` |
| Embeddings | mock / Ollama / Azure (`brain/app/retrieval/embeddings.py`) |
| Monitoring | `/health`, `/runs/metrics`, latency por step |
| Testing | `test_agent_eval.py`, `test_retrieval.py`, smoke tests |
| Deploy | CloudFormation + Docker + `infra/deploy.sh` |
| Config | Pydantic Settings, env por ambiente |

**% industrializado (auto-avaliação do repo):**

- ✅ Pipeline deployável, testável, observável
- 🔶 Métricas de negócio (P&L) — preencher após runs reais em `CASE_STUDY.md`
- 🔶 Model registry / MLflow — não incluído (scope consciente)

---

## Qualificações mínimas → posicionamento

| Requisito | FridayUGC | O que trazer além do repo |
|-----------|-----------|---------------------------|
| **+10 anos** engenharia/dados/AI | N/A — validar no CV | Trajetória, projetos anteriores, escala |
| Entrega **end-to-end cloud** | ✅ AWS GPU, S3, Docker, CI | Outros projetos cloud enterprise |
| **Liderar equipas** ágeis | ❌ não prova sozinho | Exemplos de lead, ceremonies, hiring |
| **Integração + cloud** | ✅ Phone-API-LLM-S3, multi-provider | Integrações enterprise (APIs, IAM, VPC) |

---

## Competências → checklist com evidência

| Competência (vaga) | Nível no FridayUGC | Prova |
|--------------------|------------------|-------|
| AI/ML + system design | ✅ Forte | Arquitetura brain/hands, agent loop, vision |
| **Python** | ✅ | Todo o `brain/` |
| **Spark / Java / Scala** | ⬜ Não no repo | Mencionar experiência CV; Spark = próximo passo analytics traces |
| **RAG** | ✅ | `brain/app/retrieval/` — gallery + captions |
| **Agentes** | ✅ | `/agent/step`, operator multi-fase, Android executor |
| **LangGraph** | ⬜ Não implementado | Explicar equivalência (planner + guards); roadmap claro |
| **Microsoft Agent Framework** | ✅ Opcional | `maf_loop.py`, `docs/MAF_SETUP.md` |
| **LangChain** | ⬜ Não usado | Padrões equivalentes documentados em `TECH_STACK.md` |
| **AWS** | ✅ | CloudFormation, EC2 GPU, S3 |
| **Azure** | 🔶 Ready | Embeddings + MAF backend via env |
| Pipelines de dados | 🔶 | Gallery/vision/RAG sync; não Spark |
| **MLOps / LLMOps** | ✅ | Traces, eval, health, deploy, RAG scores |
| Traduzir negócio → técnico | ✅ | UGC domain end-to-end |

**Legenda:** ✅ demonstrado no repo · 🔶 parcial / ready · ⬜ gap — abordar com honestidade + plano

---

## KPIs da vaga → como responder

| Indicador | Como FridayUGC ajuda na narrativa |
|-----------|-----------------------------------|
| **Impacto P&L** | Enquadrar: automação UGC reduz custo de operação manual / agência; métricas a capturar (posts/semana, engagement) — template em `CASE_STUDY.md` |
| **Qualidade e escalabilidade** | Eval harness, RAG fallbacks, guards, arquitetura stateless brain |
| **% deployadas / industrializadas** | Repo = industrialização de referência; CI verde, docker-compose, IaC |
| **Time-to-market** | Mock LLM → dev sem GPU; skeleton funcional antes de polish |
| **Produtividade da equipa** | Standards (protocol, schemas, tests) reduzem retrabalho — exemplo de como governaria entrega |

---

## Roteiro de entrevista (30 min demo)

1. **Problema de negócio** (2 min) — persona UGC autónoma com risco de ban  
2. **Arquitetura** (5 min) — diagrama `ARCHITECTURE.md`  
3. **Agente** (5 min) — loop observe-decide-act + approval  
4. **RAG** (5 min) — curate com `rag_hits` + caption examples  
5. **LLMOps** (5 min) — `/runs/metrics`, eval tests  
6. **Industrialização** (5 min) — deploy AWS, CI, health  
7. **Gaps + roadmap** (3 min) — LangGraph para day-plan, Spark para analytics, multi-tenant  

**Comandos demo:**

```bash
curl -s localhost:8080/health | jq '{rag_enabled, embedding_provider, rag_gallery_indexed, rag_caption_indexed, model_ready}'
curl -s -H "Authorization: Bearer $FRIDAY_API_TOKEN" localhost:8080/runs/metrics | jq .
cd brain && FRIDAY_LLM_PROVIDER=mock FRIDAY_API_TOKEN=test-token pytest tests/test_agent_eval.py tests/test_retrieval.py -q
```

---

## Carta / LinkedIn — parágrafo sugerido (PT)

> Entreguei de forma end-to-end o **Friday UGC**, um operador autónomo de conteúdo com arquitetura remote-brain/local-hands: **FastAPI + Gemma/vLLM na AWS**, agente **Android** com Accessibility API, **RAG** (curadoria de galeria e estilo de captions), **observabilidade LLMOps** (traces, métricas, eval harness) e **Microsoft Agent Framework** como engine opcional. O projeto reflecte o que procuro fazer à escala do squad: traduzir requisitos de negócio em arquitetura cloud robusta, standards de entrega e caminho claro para industrialização — com governação de risco (approval gates, budgets) desde o desenho inicial.

*(Ajustar tom e acrescentar anos de experiência / liderança reais do teu CV.)*

---

## Documentos relacionados

| Ficheiro | Uso |
|----------|-----|
| [TECH_STACK.md](./TECH_STACK.md) | Detalhe técnico EN — tools vs job posts genéricos |
| [CASE_STUDY.md](./CASE_STUDY.md) | Narrativa portfolio + métricas |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Deep dive arquitetura |
| [MAF_SETUP.md](./MAF_SETUP.md) | Microsoft Agent Framework |
