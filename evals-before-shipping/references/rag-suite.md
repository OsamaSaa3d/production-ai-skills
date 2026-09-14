# A Complete RAG Eval

The value of a RAG suite is not the score. It is the **diagnosis** — when output is wrong, knowing whether the retriever failed or the generator did. Everything below is arranged around that split.

## The five metrics, split by component

**Retriever — did we fetch the right chunks?**

| Metric | Question | Needs ground truth |
|---|---|---|
| `ContextualRelevancyMetric` | Is the retrieved context relevant to the query? | No |
| `ContextualPrecisionMetric` | Are relevant chunks ranked above irrelevant ones? | Yes (`expected_output`) |
| `ContextualRecallMetric` | Did we retrieve everything needed? | **Yes** |

**Generator — given the chunks, did we answer well?**

| Metric | Question | Needs ground truth |
|---|---|---|
| `AnswerRelevancyMetric` | Does the answer address the question? | No |
| `FaithfulnessMetric` | Is the answer grounded in the retrieved context? | No |

All score 0–1, higher is better, and pass when `score >= threshold`.

## The suite

```python
from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    ContextualRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric,
    AnswerRelevancyMetric, FaithfulnessMetric,
)

def build_case(golden):
    result = rag_pipeline(golden.input)          # your app
    return LLMTestCase(
        input=golden.input,
        actual_output=result.answer,
        retrieval_context=result.chunks,          # list[str] — what you ACTUALLY retrieved
        expected_output=golden.expected_output,   # only needed by precision/recall
    )

evaluate(
    test_cases=[build_case(g) for g in GOLDENS],
    metrics=[
        ContextualRelevancyMetric(threshold=0.7),
        ContextualPrecisionMetric(threshold=0.7),
        ContextualRecallMetric(threshold=0.8),
        FaithfulnessMetric(threshold=0.9),        # hallucination is the worst failure
        AnswerRelevancyMetric(threshold=0.7),
    ],
)
```

**`retrieval_context` must be what your pipeline actually retrieved**, in the order it retrieved it. Passing the chunks you *wish* it had retrieved, or re-running retrieval separately with different parameters, produces a suite that scores a system you are not shipping. This is the most common way a RAG eval goes quietly wrong.

## The diagnostic table

The whole point:

| Retriever scores | `FaithfulnessMetric` | Diagnosis | Where to go |
|---|---|---|---|
| Low | High | Retrieval is the problem — the generator is being honest about bad context | Chunking, embeddings, hybrid search, reranking |
| High | Low | Generation is the problem — the context was there and the model ignored it | The generation prompt |
| Low | Low | Start with the retriever; the generator can't fix what it never received | Retrieval first, re-measure |
| High | High, but answers still wrong | Your goldens, or the source documents | Check the corpus actually contains the answer |

That last row is the one people miss. If retrieval and grounding are both good and the answer is still wrong, the document is wrong, missing, or out of date. No amount of tuning fixes a corpus problem.

Sub-diagnosis within the retriever, once you know it is the retriever:

| Relevancy | Precision | Recall | Reading |
|---|---|---|---|
| Low | — | Low | Search is not finding the material at all. Embeddings, query rewriting, hybrid BM25 + dense. |
| High | Low | High | Right chunks retrieved, ranked badly. **Add a reranker.** |
| High | High | Low | Ranking is fine, coverage is not. Raise `top_k`, or chunks are too small to carry whole answers. |

`rag-pipeline-standard` has the fixes for each.

## Goldens

```python
from deepeval.dataset import EvaluationDataset, Golden

dataset = EvaluationDataset(goldens=[
    Golden(input="What is our refund window for enterprise customers?",
           expected_output="Enterprise customers have 60 days."),
    Golden(input="Can a trial account export data?",
           expected_output="No. Export requires a paid plan."),
])
```

Where to get them, best first: real user queries from logs (especially ones that produced complaints), your support queue, and questions whose answers live in a *single* known document — those make `ContextualRecallMetric` meaningful because you know exactly which chunk had to come back.

Cover four classes deliberately:

| Class | Why |
|---|---|
| Answerable from one document | Baseline; recall is unambiguous |
| **Answerable only from several documents** | Catches `top_k` set too low — the most common silent RAG failure |
| Not answerable from the corpus | Does the system say so, or invent? |
| Answerable but with a near-miss distractor in the corpus | Catches precision failures that recall hides |

The third class needs its own assertion — `expected_output` is an abstention, and `FaithfulnessMetric` alone will happily pass a confident fabrication if the retrieved context loosely supports it. Add a `GEval` criterion for "declines when the context does not contain the answer."

## Threshold tuning

Don't invent thresholds. Derive them.

1. **Run once with `threshold=None`** on every metric — score-only mode, computed and tracked, no pass/fail opinion.
2. **Read the distribution.** Where do known-good cases score? Known-bad?
3. **Set the threshold below your known-good floor**, not at a round number.
4. **Re-check after any pipeline change.** Thresholds are calibrated against a system, not against a metric.

Starting points, to be replaced by your own numbers:

| Metric | Start | Rationale |
|---|---|---|
| `FaithfulnessMetric` | 0.9 | Hallucination is the failure that destroys trust |
| `ContextualRecallMetric` | 0.8 | Missing evidence is unrecoverable downstream |
| `ContextualRelevancyMetric` | 0.7 | Some irrelevant context is tolerable |
| `ContextualPrecisionMetric` | 0.7 | Matters most when `top_k` is small |
| `AnswerRelevancyMetric` | 0.7 | Catches evasive and off-topic answers |

## Comparing retrieval strategies

The suite's second job: deciding between configurations with evidence instead of intuition.

```python
STRATEGIES = {
    "dense_only":      lambda q: dense(q, k=20),
    "hybrid_rrf":      lambda q: rrf(bm25(q, k=50), dense(q, k=50))[:20],
    "hybrid_reranked": lambda q: rerank(q, rrf(bm25(q, k=100), dense(q, k=100)), top_n=20),
}

for name, retrieve in STRATEGIES.items():
    cases = [LLMTestCase(input=g.input,
                         actual_output=generate(g.input, retrieve(g.input)),
                         retrieval_context=retrieve(g.input),
                         expected_output=g.expected_output)
             for g in GOLDENS]
    print(name, evaluate(test_cases=cases, metrics=RETRIEVER_METRICS))
```

Record latency and cost per strategy alongside the scores. A reranker that adds four points of precision and 400ms may or may not be worth it, and that is a product decision the numbers should inform rather than make.

Sweep `top_k` and `rerank_top_n` the same way. Do not assume 20 is optimal because it looks tidy — treat them as evaluation parameters.

## The two that run in production

`FaithfulnessMetric` and `AnswerRelevancyMetric` are referenceless, so they run unchanged on live traffic. If you only pick two, pick these.

```python
DEV_METRICS  = [ContextualRelevancyMetric(), ContextualPrecisionMetric(),
                ContextualRecallMetric(), FaithfulnessMetric(), AnswerRelevancyMetric()]
PROD_METRICS = [FaithfulnessMetric(threshold=0.9), AnswerRelevancyMetric(threshold=0.7)]
```

Sample production rather than scoring every request — judge calls cost real money. Alert on the *rate*, not on individual failures.

`ContextualRecallMetric` and `ContextualPrecisionMetric` cannot run in production: they need `expected_output`, which live traffic does not have.

## Domain criteria with GEval

Built-ins cover generic quality. Anything domain-specific needs a written criterion:

```python
from deepeval.metrics import GEval
from deepeval.test_case import SingleTurnParams

policy_grounding = GEval(
    name="PolicyGrounding",
    criteria=("Determine whether the actual output's claims about company policy "
              "are supported by the retrieval context. Penalize any policy "
              "statement not traceable to the context."),
    evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
    threshold=0.8,
)
```

Stay within the five-metric cap. Two or three generic metrics plus one or two custom criteria. More metrics means less signal, not more — and each one is a judge call per case.

## Pitfalls specific to RAG evals

**Scoring a retriever you're not shipping.** Covered above, and worth repeating.

**Goldens written from the documents.** If you wrote the question while reading the chunk, you wrote a question whose vocabulary matches the chunk. Real users don't. Pull inputs from logs.

**No multi-document cases.** A suite of single-document questions passes at `top_k=3` and ships a system that fails on every question needing two sources.

**Uncalibrated judges.** Model-based metrics need checking against human labels before you trust them. Turn on `verbose_mode=True` and read `.reason` on a sample.

**Corpus drift.** The documents change; the goldens do not. Re-validate `expected_output` against the corpus on a schedule, or your suite starts failing for reasons that are not regressions.
