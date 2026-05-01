;; ==========================================================================
;; TRLCBench Hospital Problem 02: Two Batches, Shared Autoclave, Two ORs
;;
;; Semi-ergodic: if b1 misses OR1 window, it can reroute to OR2 (staggered).
;; But both batches need the same autoclave → sequencing matters.
;;
;; OR1 window: [0, 28]   (for b1)
;; OR2 window: [10, 38]  (for b2, staggered)
;; OR2 also accepts b1 as fallback (semi-ergodic recovery)
;;
;; Key tension: autoclave is shared. If b1 sterilizes first, b2 must wait.
;; If b2 sterilizes first, b1 might miss OR1 but can fall back to OR2.
;; ==========================================================================

(define (problem hospital-p02-two-batches)
  (:domain hospital-sterilization)

  (:objects
    b1 b2 - batch
    intake decontam_st wash_st sterilize_st cool_st pack_st or1_st or2_st - station
    ac1 - autoclave
    or1 or2 - or_room
  )

  (:init
    ;; Both batches start dirty at intake
    (batch-at b1 intake) (batch-dirty b1)
    (batch-at b2 intake) (batch-dirty b2)

    ;; Connectivity (shared pipeline, branching at pack_st to ORs)
    (connected intake decontam_st)
    (connected decontam_st wash_st)
    (connected wash_st sterilize_st)
    (connected sterilize_st cool_st)
    (connected cool_st pack_st)
    (connected pack_st or1_st)
    (connected pack_st or2_st)

    ;; Transfer times
    (= (transfer-time intake decontam_st) 1)
    (= (transfer-time decontam_st wash_st) 1)
    (= (transfer-time wash_st sterilize_st) 1)
    (= (transfer-time sterilize_st cool_st) 1)
    (= (transfer-time cool_st pack_st) 1)
    (= (transfer-time pack_st or1_st) 2)
    (= (transfer-time pack_st or2_st) 3)

    ;; Bounded durations — b1
    (= (decontaminate-min b1) 3) (= (decontaminate-max b1) 8)
    (= (wash-min b1) 2)          (= (wash-max b1) 6)
    (= (sterilize-min b1) 5)     (= (sterilize-max b1) 12)
    (= (cool-min b1) 3)
    (= (pack-min b1) 1)          (= (pack-max b1) 4)

    ;; Bounded durations — b2
    (= (decontaminate-min b2) 3) (= (decontaminate-max b2) 8)
    (= (wash-min b2) 2)          (= (wash-max b2) 6)
    (= (sterilize-min b2) 5)     (= (sterilize-max b2) 12)
    (= (cool-min b2) 3)
    (= (pack-min b2) 1)          (= (pack-max b2) 4)

    ;; Single shared autoclave
    (autoclave-free ac1)
    (autoclave-at ac1 sterilize_st)

    ;; OR1: primary for b1, window [0, 28]
    (or-window-open or1)
    (or-needs-batch or1 b1)
    (or-at or1 or1_st)
    (at 28 (not (or-window-open or1)))

    ;; OR2: primary for b2, window [10, 38] — also accepts b1 (fallback)
    (or-at or2 or2_st)
    (or-needs-batch or2 b2)
    (or-needs-batch or2 b1)  ;; <-- semi-ergodic: b1 can reroute here
    (at 10 (or-window-open or2))
    (at 38 (not (or-window-open or2)))
  )

  (:goal
    (and
      (batch-delivered b1)
      (batch-delivered b2)
    )
  )
)
