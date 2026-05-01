;; ==========================================================================
;; TRLCBench Rover Problem 02: Two Samples, Shared Window
;;
;; Topology:  wp0 --3-- wp1 --3-- wp2 --3-- wp3
;;                        \--2-- wp4
;;            (base)      (fork)  (sample1)  (comm)
;;                                (sample2 at wp4)
;;
;; Two samples must be collected, analyzed, and transmitted
;; through the same comm window. Forces sequencing decisions.
;; Comm window: [0, 30]
;; ==========================================================================

(define (problem rover-p02-two-samples)
  (:domain rover-temporal)

  (:objects
    r1 - rover
    wp0 wp1 wp2 wp3 wp4 - waypoint
    s1 s2 - sample
  )

  (:init
    (at r1 wp0)
    (can-analyze r1)

    ;; Topology: branching at wp1
    (connected wp0 wp1) (connected wp1 wp0)
    (connected wp1 wp2) (connected wp2 wp1)
    (connected wp2 wp3) (connected wp3 wp2)
    (connected wp1 wp4) (connected wp4 wp1)

    ;; Distances
    (= (distance wp0 wp1) 3)  (= (distance wp1 wp0) 3)
    (= (distance wp1 wp2) 3)  (= (distance wp2 wp1) 3)
    (= (distance wp2 wp3) 3)  (= (distance wp3 wp2) 3)
    (= (distance wp1 wp4) 2)  (= (distance wp4 wp1) 2)

    ;; Move costs
    (= (move-cost wp0 wp1) 10) (= (move-cost wp1 wp0) 10)
    (= (move-cost wp1 wp2) 10) (= (move-cost wp2 wp1) 10)
    (= (move-cost wp2 wp3) 10) (= (move-cost wp3 wp2) 10)
    (= (move-cost wp1 wp4) 8)  (= (move-cost wp4 wp1) 8)

    ;; Samples
    (sample-at s1 wp2)
    (= (collection-duration s1) 3)
    (= (analysis-duration s1) 4)
    (= (transmit-duration s1) 2)

    (sample-at s2 wp4)
    (= (collection-duration s2) 2)
    (= (analysis-duration s2) 3)
    (= (transmit-duration s2) 2)

    ;; Battery
    (= (battery-level r1) 100)
    (charging-station wp0)

    ;; Comm window — larger but still tight for two samples
    (comm-window-open wp3)
    (at 30 (not (comm-window-open wp3)))
  )

  (:goal
    (and
      (data-transmitted s1)
      (data-transmitted s2)
    )
  )
)
