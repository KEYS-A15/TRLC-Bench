;; ==========================================================================
;; TRLCBench Rover Problem 01: Single Sample, Tight Window
;;
;; Topology:  wp0 --3-- wp1 --3-- wp2 --3-- wp3
;;            (base)              (sample)   (comm)
;;
;; Comm window: [0, 18] at wp3
;; Battery: 100 (sufficient but not generous)
;; ==========================================================================

(define (problem rover-p01-single-sample)
  (:domain rover-temporal)

  (:objects
    r1 - rover
    wp0 wp1 wp2 wp3 - waypoint
    s1 - sample
  )

  (:init
    (at r1 wp0)
    (can-analyze r1)
    (available r1)

    ;; Topology: linear chain
    (connected wp0 wp1) (connected wp1 wp0)
    (connected wp1 wp2) (connected wp2 wp1)
    (connected wp2 wp3) (connected wp3 wp2)

    ;; Distances
    (= (distance wp0 wp1) 3)  (= (distance wp1 wp0) 3)
    (= (distance wp1 wp2) 3)  (= (distance wp2 wp1) 3)
    (= (distance wp2 wp3) 3)  (= (distance wp3 wp2) 3)

    ;; Movement costs
    (= (move-cost wp0 wp1) 10) (= (move-cost wp1 wp0) 10)
    (= (move-cost wp1 wp2) 10) (= (move-cost wp2 wp1) 10)
    (= (move-cost wp2 wp3) 10) (= (move-cost wp3 wp2) 10)

    ;; Sample
    (sample-at s1 wp2)
    (= (collection-duration s1) 3)
    (= (analysis-duration s1) 4)
    (= (transmit-duration s1) 2)

    ;; Battery
    (= (battery-level r1) 100)

    ;; Charging station at base
    (charging-station wp0)

    ;; Communication window: open from t=0, closes at t=18 (TIL)
    (comm-window-open wp3)
    (at 19 (not (comm-window-open wp3)))
  )

  (:goal
    (data-transmitted s1)
  )
)
