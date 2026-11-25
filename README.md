# TRLC Bench

TRLC Bench is a benchmark for **Temporal Repair with Learned Critique** and a
harness for evaluating verifier-guided repair. The current prototype includes
rover and hospital domains, with four plan fixtures and three disruption classes:
duration perturbation (A), changed external constraints (B), and action failure
with cascading effects (C).

```sh
uv run trlc-bench run --config configs/hospital_p01.yaml --plan plans/hospital/p01_valid.plan
```

The CLI includes the existing Anthropic strategy when running the matrix.
Without `ANTHROPIC_API_KEY`, that strategy returns the disrupted schedule with a
failed repair status. Ignore that row when comparing offline baselines.

## Research question

Can retained commitments make overlap necessary for repair even when the same
disrupted problem admits a sequential plan with those commitments released?
Compare three feasibility checks on matched instances: sequential planning with
commitments released, sequential repair with commitments retained, and concurrent
repair with commitments retained. A witness requires a feasible first and third
case and a proved infeasible second case. Timeouts are inconclusive. Tight,
single-rover cases can measure sensitivity to timing and slack separately from
required concurrency. See [Cushing et al. on required concurrency](https://ijcai.org/proceedings/2007/299).

The proposed method uses a learned critic to turn grounded validator diagnostics
and repair-quality signals into feedback for the next revision. Compare symbolic
repair, one-shot model repair, and verifier-guided repair. Within the iterative
loop, compare raw verifier feedback with learned critique using the same model,
repair budget, and final validator. Report verified success by disruption class,
verifier calls, repair effort, and the quality profile of valid repairs.

## Prototype status

- Class B passes the shortened deadline to both repair and scoring. The PDDL
  window itself still needs to be updated for semantic evaluation.
- `rule_based` is a fixed-order operator baseline. The Anthropic loop sends
  structural violations back to the model. An independently tested learned
  critic and a semantic acceptance gate are still open.
- The structural validator can accept plans with invalid PDDL transitions or
  unmet goals. Fixed-duration checking is currently disabled. TRLCScore in
  code gives partial credit to invalid candidates, which differs from the
  hard-gated equation in the historical write-up.
- The difficulty generator, exact repair oracle, external baseline integration,
  and broader domain suite are roadmap items in this checkout.
