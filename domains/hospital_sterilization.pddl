;; ==========================================================================
;; TRLCBench Domain 2: Hospital Instrument Sterilization Pipeline
;; 
;; Lineage: Matchcellar (IPC 2014 temporal track)
;; Extended with bounded-duration constraints [d_min, d_max]
;; 
;; Properties:
;;   - Semi-ergodic: batch can reroute to another OR if window missed,
;;     but if ALL OR windows close, batch is dead
;;   - Bounded durations: each pipeline stage has min AND max duration
;;     (too short = contaminated, too long = degraded)
;;   - Concurrency-necessary: multiple batches share autoclaves
;;   - Multiple overlapping deadlines: each OR has its own window
;;
;; Novel contribution:
;;   Bounded duration constraint [d_min, d_max] is absent from IPC
;;   benchmarks and existing repair literature. Actions that complete
;;   too quickly are INVALID — a failure mode classical repair ignores.
;; ==========================================================================

(define (domain hospital-sterilization)
  (:requirements :durative-actions :typing :numeric-fluents :duration-inequalities)

  (:types
    batch station or_room autoclave - object
  )

  (:predicates
    ;; Batch state tracking (pipeline stages)
    (batch-at ?b - batch ?s - station)
    (batch-dirty ?b - batch)
    (batch-decontaminated ?b - batch)
    (batch-washed ?b - batch)
    (batch-sterilized ?b - batch)
    (batch-cooled ?b - batch)
    (batch-packed ?b - batch)
    (batch-delivered ?b - batch)

    ;; Station connectivity
    (connected ?from ?to - station)

    ;; Resource availability
    (autoclave-free ?a - autoclave)
    (autoclave-at ?a - autoclave ?s - station)

    ;; OR scheduling
    (or-window-open ?o - or_room)
    (or-needs-batch ?o - or_room ?b - batch)
    (or-at ?o - or_room ?s - station)

    ;; Batch processing state (mutual exclusion)
    (batch-processing ?b - batch)

    ;; Transfer state
    (batch-in-transit ?b - batch)
  )

  (:functions
    (transfer-time ?from ?to - station)

    ;; Bounded durations per batch (set in problem file)
    (decontaminate-min ?b - batch)
    (decontaminate-max ?b - batch)
    (wash-min ?b - batch)
    (wash-max ?b - batch)
    (sterilize-min ?b - batch)
    (sterilize-max ?b - batch)
    (cool-min ?b - batch)
    (pack-min ?b - batch)
    (pack-max ?b - batch)
  )

  ;; -------------------------------------------------------------------
  ;; TRANSFER: move batch between stations. Duration = transfer-time.
  ;; -------------------------------------------------------------------
  (:durative-action transfer
    :parameters (?b - batch ?from ?to - station)
    :duration (= ?duration (transfer-time ?from ?to))
    :condition (and
      (at start (batch-at ?b ?from))
      (at start (connected ?from ?to))
      (at start (not (batch-processing ?b)))
      (at start (not (batch-in-transit ?b)))
    )
    :effect (and
      (at start (not (batch-at ?b ?from)))
      (at start (batch-in-transit ?b))
      (at end (batch-at ?b ?to))
      (at end (not (batch-in-transit ?b)))
    )
  )

  ;; -------------------------------------------------------------------
  ;; DECONTAMINATE: bounded [d_min, d_max]. Too short = biohazard.
  ;; -------------------------------------------------------------------
  (:durative-action decontaminate
    :parameters (?b - batch ?s - station)
    :duration (and
      (>= ?duration (decontaminate-min ?b))
      (<= ?duration (decontaminate-max ?b))
    )
    :condition (and
      (at start (batch-at ?b ?s))
      (at start (batch-dirty ?b))
      (at start (not (batch-processing ?b)))
      (at start (not (batch-in-transit ?b)))
      (over all (batch-at ?b ?s))
    )
    :effect (and
      (at start (batch-processing ?b))
      (at start (not (batch-dirty ?b)))
      (at end (not (batch-processing ?b)))
      (at end (batch-decontaminated ?b))
    )
  )

  ;; -------------------------------------------------------------------
  ;; WASH: bounded [d_min, d_max]. Too short = residue. Too long = corrosion.
  ;; -------------------------------------------------------------------
  (:durative-action wash
    :parameters (?b - batch ?s - station)
    :duration (and
      (>= ?duration (wash-min ?b))
      (<= ?duration (wash-max ?b))
    )
    :condition (and
      (at start (batch-at ?b ?s))
      (at start (batch-decontaminated ?b))
      (at start (not (batch-washed ?b)))
      (at start (not (batch-processing ?b)))
      (at start (not (batch-in-transit ?b)))
      (over all (batch-at ?b ?s))
    )
    :effect (and
      (at start (batch-processing ?b))
      (at end (not (batch-processing ?b)))
      (at end (batch-washed ?b))
    )
  )

  ;; -------------------------------------------------------------------
  ;; STERILIZE: bounded [d_min, d_max]. Requires autoclave (shared resource).
  ;; Too short = not sterile. Too long = material fatigue.
  ;; -------------------------------------------------------------------
  (:durative-action sterilize
    :parameters (?b - batch ?s - station ?a - autoclave)
    :duration (and
      (>= ?duration (sterilize-min ?b))
      (<= ?duration (sterilize-max ?b))
    )
    :condition (and
      (at start (batch-at ?b ?s))
      (at start (batch-washed ?b))
      (at start (not (batch-sterilized ?b)))
      (at start (not (batch-processing ?b)))
      (at start (not (batch-in-transit ?b)))
      (at start (autoclave-free ?a))
      (at start (autoclave-at ?a ?s))
      (over all (batch-at ?b ?s))
    )
    :effect (and
      (at start (batch-processing ?b))
      (at start (not (autoclave-free ?a)))
      (at end (not (batch-processing ?b)))
      (at end (autoclave-free ?a))
      (at end (batch-sterilized ?b))
    )
  )

  ;; -------------------------------------------------------------------
  ;; COOL: lower-bounded only (>= cool-min). No upper bound — can wait.
  ;; This is intentional slack in the pipeline.
  ;; -------------------------------------------------------------------
  (:durative-action cool
    :parameters (?b - batch ?s - station)
    :duration (>= ?duration (cool-min ?b))
    :condition (and
      (at start (batch-at ?b ?s))
      (at start (batch-sterilized ?b))
      (at start (not (batch-cooled ?b)))
      (at start (not (batch-processing ?b)))
      (at start (not (batch-in-transit ?b)))
      (over all (batch-at ?b ?s))
    )
    :effect (and
      (at start (batch-processing ?b))
      (at end (not (batch-processing ?b)))
      (at end (batch-cooled ?b))
    )
  )

  ;; -------------------------------------------------------------------
  ;; PACK: bounded [d_min, d_max]. Too short = improper seal.
  ;; -------------------------------------------------------------------
  (:durative-action pack
    :parameters (?b - batch ?s - station)
    :duration (and
      (>= ?duration (pack-min ?b))
      (<= ?duration (pack-max ?b))
    )
    :condition (and
      (at start (batch-at ?b ?s))
      (at start (batch-cooled ?b))
      (at start (not (batch-packed ?b)))
      (at start (not (batch-processing ?b)))
      (at start (not (batch-in-transit ?b)))
      (over all (batch-at ?b ?s))
    )
    :effect (and
      (at start (batch-processing ?b))
      (at end (not (batch-processing ?b)))
      (at end (batch-packed ?b))
    )
  )

  ;; -------------------------------------------------------------------
  ;; DELIVER: batch goes to OR. OR window must be open (over all).
  ;; This is the hard external deadline, analogous to rover's comm window.
  ;; -------------------------------------------------------------------
  (:durative-action deliver
    :parameters (?b - batch ?s - station ?o - or_room ?os - station)
    :duration (= ?duration (transfer-time ?s ?os))
    :condition (and
      (at start (batch-at ?b ?s))
      (at start (batch-packed ?b))
      (at start (not (batch-delivered ?b)))
      (at start (not (batch-processing ?b)))
      (at start (not (batch-in-transit ?b)))
      (at start (or-window-open ?o))
      (at start (or-needs-batch ?o ?b))
      (at start (or-at ?o ?os))
      (over all (or-window-open ?o))
    )
    :effect (and
      (at start (not (batch-at ?b ?s)))
      (at start (batch-in-transit ?b))
      (at end (batch-at ?b ?os))
      (at end (not (batch-in-transit ?b)))
      (at end (batch-delivered ?b))
    )
  )
)
