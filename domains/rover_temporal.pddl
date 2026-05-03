(define (domain rover-temporal)
  (:requirements :durative-actions :typing :numeric-fluents :timed-initial-literals)

  (:types
    rover waypoint sample - object
  )

  (:predicates
    (at ?r - rover ?w - waypoint)
    (connected ?from ?to - waypoint)
    (sample-at ?s - sample ?w - waypoint)
    (sample-collected ?s - sample)
    (sample-analyzed ?s - sample)
    (can-analyze ?r - rover)
    (comm-window-open ?w - waypoint)
    (data-transmitted ?s - sample)
    (charging-station ?w - waypoint)
    (available ?r - rover)
  )

  (:functions
    (battery-level ?r - rover)
    (move-cost ?from ?to - waypoint)
    (distance ?from ?to - waypoint)
    (analysis-duration ?s - sample)
    (collection-duration ?s - sample)
    (transmit-duration ?s - sample)
  )

  (:durative-action navigate
    :parameters (?r - rover ?from ?to - waypoint)
    :duration (= ?duration (distance ?from ?to))
    :condition (and
      (at start (at ?r ?from))
      (at start (connected ?from ?to))
      (at start (available ?r))
      (at start (>= (battery-level ?r) (move-cost ?from ?to)))
    )
    :effect (and
      (at start (not (at ?r ?from)))
      (at start (not (available ?r)))
      (at end (at ?r ?to))
      (at end (available ?r))
      (at end (decrease (battery-level ?r) (move-cost ?from ?to)))
    )
  )

  (:durative-action collect-sample
    :parameters (?r - rover ?s - sample ?w - waypoint)
    :duration (= ?duration (collection-duration ?s))
    :condition (and
      (at start (available ?r))
      (at start (sample-at ?s ?w))
      (over all (at ?r ?w))
    )
    :effect (and
      (at start (not (available ?r)))
      (at end (available ?r))
      (at end (sample-collected ?s))
    )
  )

  (:durative-action analyze-sample
    :parameters (?r - rover ?s - sample ?w - waypoint)
    :duration (= ?duration (analysis-duration ?s))
    :condition (and
      (at start (available ?r))
      (at start (sample-collected ?s))
      (at start (can-analyze ?r))
      (over all (at ?r ?w))
    )
    :effect (and
      (at start (not (available ?r)))
      (at end (available ?r))
      (at end (sample-analyzed ?s))
    )
  )

  (:durative-action transmit-data
    :parameters (?r - rover ?s - sample ?w - waypoint)
    :duration (= ?duration (transmit-duration ?s))
    :condition (and
      (at start (available ?r))
      (at start (sample-analyzed ?s))
      (over all (at ?r ?w))
      (over all (comm-window-open ?w))
    )
    :effect (and
      (at start (not (available ?r)))
      (at end (available ?r))
      (at end (data-transmitted ?s))
    )
  )

  (:durative-action recharge
    :parameters (?r - rover ?w - waypoint)
    :duration (= ?duration 5)
    :condition (and
      (at start (available ?r))
      (at start (charging-station ?w))
      (over all (at ?r ?w))
    )
    :effect (and
      (at start (not (available ?r)))
      (at end (available ?r))
      (at end (assign (battery-level ?r) 100))
    )
  )
)
