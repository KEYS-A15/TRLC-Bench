;; ==========================================================================
;; TRLCBench Hospital Problem 01: Single Batch, Single OR
;;
;; Layout:
;;   intake --1-- decontam_st --1-- wash_st --1-- sterilize_st
;;                                                  --1-- cool_st --1-- pack_st --2-- or1_st
;;
;; Pipeline: decontaminate[3,8] → wash[2,6] → sterilize[5,12] → cool[3,∞] → pack[1,4] → deliver
;;
;; Choosing minimum durations: 3+2+5+3+1 = 14 time in processing + 6 transfer = 20
;; OR window: [0, 28] — gives 8 units of total slack
;; ==========================================================================

(define (problem hospital-p01-single-batch)
  (:domain hospital-sterilization)

  (:objects
    b1 - batch
    intake decontam_st wash_st sterilize_st cool_st pack_st or1_st - station
    ac1 - autoclave
    or1 - or_room
  )

  (:init
    ;; Batch starts at intake, dirty
    (batch-at b1 intake)
    (batch-dirty b1)

    ;; Station connectivity (linear pipeline)
    (connected intake decontam_st)
    (connected decontam_st wash_st)
    (connected wash_st sterilize_st)
    (connected sterilize_st cool_st)
    (connected cool_st pack_st)
    (connected pack_st or1_st)

    ;; Transfer times between stations
    (= (transfer-time intake decontam_st) 1)
    (= (transfer-time decontam_st wash_st) 1)
    (= (transfer-time wash_st sterilize_st) 1)
    (= (transfer-time sterilize_st cool_st) 1)
    (= (transfer-time cool_st pack_st) 1)
    (= (transfer-time pack_st or1_st) 2)

    ;; Bounded durations for b1
    (= (decontaminate-min b1) 3) (= (decontaminate-max b1) 8)
    (= (wash-min b1) 2)          (= (wash-max b1) 6)
    (= (sterilize-min b1) 5)     (= (sterilize-max b1) 12)
    (= (cool-min b1) 3)
    (= (pack-min b1) 1)          (= (pack-max b1) 4)

    ;; Autoclave at sterilize station
    (autoclave-free ac1)
    (autoclave-at ac1 sterilize_st)

    ;; OR1 window and requirements
    (or-window-open or1)
    (or-needs-batch or1 b1)
    (or-at or1 or1_st)
    (at 28 (not (or-window-open or1)))
  )

  (:goal
    (and
      (batch-delivered b1)
    )
  )
)
