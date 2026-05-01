;; ==========================================================================
;; TRLCBench Domain 1: Mars Rover Temporal
;; 
;; Lineage: IPC 2002 Rovers (Fox & Long, PDDL2.1, JAIR 2003)
;; Modified for TRLCBench: simplified to expose genuine temporal structure
;; 
;; Properties:
;;   - Non-ergodic: comm window closes permanently (TIL)
;;   - Duration-sensitive: navigate duration = distance (structural)
;;   - Concurrency-constrained: rover cannot move and work simultaneously
;;   - Sequential dependency: collect → analyze → transmit
;;
;; Novel contribution over IPC original:
;;   Battery as numeric fluent creating resource-temporal coupling.
;;   Original IPC rovers had no resource depletion during movement.
;; ==========================================================================

(define (domain rover-temporal)
  (:requirements :durative-actions :typing :numeric-fluents :duration-inequalities)

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
    (moving ?r - rover)
    (working ?r - rover)
  )

  (:functions
    (battery-level ?r - rover)
    (move-cost ?from ?to - waypoint)
    (distance ?from ?to - waypoint)
    (analysis-duration ?s - sample)
    (collection-duration ?s - sample)
    (transmit-duration ?s - sample)
  )

  ;; -------------------------------------------------------------------
  ;; NAVIGATE: duration = distance. Battery drains. Cannot overlap work.
  ;; -------------------------------------------------------------------
  (:durative-action navigate
    :parameters (?r - rover ?from ?to - waypoint)
    :duration (= ?duration (distance ?from ?to))
    :condition (and
      (at start (at ?r ?from))
      (at start (connected ?from ?to))
      (at start (>= (battery-level ?r) (move-cost ?from ?to)))
      (at start (not (moving ?r)))
      (at start (not (working ?r)))
      (over all (not (working ?r)))
    )
    :effect (and
      (at start (not (at ?r ?from)))
      (at start (moving ?r))
      (at end (at ?r ?to))
      (at end (not (moving ?r)))
      (at end (decrease (battery-level ?r) (move-cost ?from ?to)))
    )
  )

  ;; -------------------------------------------------------------------
  ;; COLLECT-SAMPLE: rover must be at sample location for full duration
  ;; -------------------------------------------------------------------
  (:durative-action collect-sample
    :parameters (?r - rover ?s - sample ?w - waypoint)
    :duration (= ?duration (collection-duration ?s))
    :condition (and
      (at start (at ?r ?w))
      (at start (sample-at ?s ?w))
      (at start (not (sample-collected ?s)))
      (at start (not (working ?r)))
      (at start (not (moving ?r)))
      (over all (at ?r ?w))
      (over all (not (moving ?r)))
    )
    :effect (and
      (at start (working ?r))
      (at end (not (working ?r)))
      (at end (sample-collected ?s))
    )
  )

  ;; -------------------------------------------------------------------
  ;; ANALYZE-SAMPLE: requires collected. Rover stationary for duration.
  ;; -------------------------------------------------------------------
  (:durative-action analyze-sample
    :parameters (?r - rover ?s - sample ?w - waypoint)
    :duration (= ?duration (analysis-duration ?s))
    :condition (and
      (at start (at ?r ?w))
      (at start (sample-collected ?s))
      (at start (not (sample-analyzed ?s)))
      (at start (can-analyze ?r))
      (at start (not (working ?r)))
      (at start (not (moving ?r)))
      (over all (at ?r ?w))
      (over all (not (moving ?r)))
    )
    :effect (and
      (at start (working ?r))
      (at end (not (working ?r)))
      (at end (sample-analyzed ?s))
    )
  )

  ;; -------------------------------------------------------------------
  ;; TRANSMIT-DATA: comm window must be open for ENTIRE duration (over all).
  ;; This is the hard temporal constraint. Window is controlled by TIL.
  ;; -------------------------------------------------------------------
  (:durative-action transmit-data
    :parameters (?r - rover ?s - sample ?w - waypoint)
    :duration (= ?duration (transmit-duration ?s))
    :condition (and
      (at start (at ?r ?w))
      (at start (sample-analyzed ?s))
      (at start (not (data-transmitted ?s)))
      (at start (comm-window-open ?w))
      (at start (not (working ?r)))
      (at start (not (moving ?r)))
      (over all (comm-window-open ?w))
      (over all (at ?r ?w))
      (over all (not (moving ?r)))
    )
    :effect (and
      (at start (working ?r))
      (at end (not (working ?r)))
      (at end (data-transmitted ?s))
    )
  )

  ;; -------------------------------------------------------------------
  ;; RECHARGE: only at charging stations, takes time
  ;; -------------------------------------------------------------------
  (:durative-action recharge
    :parameters (?r - rover ?w - waypoint)
    :duration (= ?duration 5)
    :condition (and
      (at start (at ?r ?w))
      (at start (charging-station ?w))
      (at start (not (moving ?r)))
      (at start (not (working ?r)))
      (over all (at ?r ?w))
      (over all (not (moving ?r)))
    )
    :effect (and
      (at start (working ?r))
      (at end (not (working ?r)))
      (at end (assign (battery-level ?r) 100))
    )
  )
)
