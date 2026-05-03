(define (domain hospital-sterilization)
  (:requirements :durative-actions :typing :numeric-fluents :duration-inequalities :timed-initial-literals)

  (:types
    batch station or_room autoclave - object
  )

  (:predicates
    ;; Batch state tracking
    (batch-at ?b - batch ?s - station)
    (batch-dirty ?b - batch)
    (batch-decontaminated ?b - batch)
    (batch-washed ?b - batch)
    (batch-sterilized ?b - batch)
    (batch-cooled ?b - batch)
    (batch-packed ?b - batch)
    (batch-delivered ?b - batch)

    ;; Positive mutex predicate for OPTIC compatibility
    (batch-available ?b - batch)

    ;; Station connectivity
    (connected ?from ?to - station)

    ;; Station-type predicates — enforce correct processing locations
    (is-decontam-station ?s - station)
    (is-wash-station ?s - station)
    (is-sterilize-station ?s - station)
    (is-cool-station ?s - station)
    (is-pack-station ?s - station)

    ;; Resource availability
    (autoclave-free ?a - autoclave)
    (autoclave-at ?a - autoclave ?s - station)

    ;; OR scheduling
    (or-window-open ?o - or_room)
    (or-needs-batch ?o - or_room ?b - batch)
    (or-at ?o - or_room ?s - station)
  )

  (:functions
    (transfer-time ?from ?to - station)
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

  (:durative-action transfer
    :parameters (?b - batch ?from ?to - station)
    :duration (= ?duration (transfer-time ?from ?to))
    :condition (and
      (at start (batch-at ?b ?from))
      (at start (connected ?from ?to))
      (at start (batch-available ?b))
    )
    :effect (and
      (at start (not (batch-at ?b ?from)))
      (at start (not (batch-available ?b)))
      (at end (batch-at ?b ?to))
      (at end (batch-available ?b))
    )
  )

  (:durative-action decontaminate
    :parameters (?b - batch ?s - station)
    :duration (and
      (>= ?duration (decontaminate-min ?b))
      (<= ?duration (decontaminate-max ?b))
    )
    :condition (and
      (at start (batch-at ?b ?s))
      (at start (batch-dirty ?b))
      (at start (batch-available ?b))
      (at start (is-decontam-station ?s))
      (over all (batch-at ?b ?s))
    )
    :effect (and
      (at start (not (batch-available ?b)))
      (at start (not (batch-dirty ?b)))
      (at end (batch-available ?b))
      (at end (batch-decontaminated ?b))
    )
  )

  (:durative-action wash
    :parameters (?b - batch ?s - station)
    :duration (and
      (>= ?duration (wash-min ?b))
      (<= ?duration (wash-max ?b))
    )
    :condition (and
      (at start (batch-at ?b ?s))
      (at start (batch-decontaminated ?b))
      (at start (batch-available ?b))
      (at start (is-wash-station ?s))
      (over all (batch-at ?b ?s))
    )
    :effect (and
      (at start (not (batch-available ?b)))
      (at end (batch-available ?b))
      (at end (batch-washed ?b))
    )
  )

  (:durative-action sterilize
    :parameters (?b - batch ?s - station ?a - autoclave)
    :duration (and
      (>= ?duration (sterilize-min ?b))
      (<= ?duration (sterilize-max ?b))
    )
    :condition (and
      (at start (batch-at ?b ?s))
      (at start (batch-washed ?b))
      (at start (batch-available ?b))
      (at start (is-sterilize-station ?s))
      (at start (autoclave-free ?a))
      (at start (autoclave-at ?a ?s))
      (over all (batch-at ?b ?s))
    )
    :effect (and
      (at start (not (batch-available ?b)))
      (at start (not (autoclave-free ?a)))
      (at end (batch-available ?b))
      (at end (autoclave-free ?a))
      (at end (batch-sterilized ?b))
    )
  )

  (:durative-action cool
    :parameters (?b - batch ?s - station)
    :duration (= ?duration (cool-min ?b))
    :condition (and
      (at start (batch-at ?b ?s))
      (at start (batch-sterilized ?b))
      (at start (batch-available ?b))
      (at start (is-cool-station ?s))
      (over all (batch-at ?b ?s))
    )
    :effect (and
      (at start (not (batch-available ?b)))
      (at end (batch-available ?b))
      (at end (batch-cooled ?b))
    )
  )

  (:durative-action pack
    :parameters (?b - batch ?s - station)
    :duration (and
      (>= ?duration (pack-min ?b))
      (<= ?duration (pack-max ?b))
    )
    :condition (and
      (at start (batch-at ?b ?s))
      (at start (batch-cooled ?b))
      (at start (batch-available ?b))
      (at start (is-pack-station ?s))
      (over all (batch-at ?b ?s))
    )
    :effect (and
      (at start (not (batch-available ?b)))
      (at end (batch-available ?b))
      (at end (batch-packed ?b))
    )
  )

  (:durative-action deliver
    :parameters (?b - batch ?s - station ?o - or_room ?os - station)
    :duration (= ?duration (transfer-time ?s ?os))
    :condition (and
      (at start (batch-at ?b ?s))
      (at start (batch-packed ?b))
      (at start (batch-available ?b))
      (at start (or-window-open ?o))
      (at start (or-needs-batch ?o ?b))
      (at start (or-at ?o ?os))
      (over all (or-window-open ?o))
    )
    :effect (and
      (at start (not (batch-at ?b ?s)))
      (at start (not (batch-available ?b)))
      (at end (batch-at ?b ?os))
      (at end (batch-available ?b))
      (at end (batch-delivered ?b))
    )
  )
)
