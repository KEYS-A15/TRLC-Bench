(define (problem hospital-p01-single-batch)
  (:domain hospital-sterilization)

  (:objects
    b1 - batch
    intake decontam_st wash_st sterilize_st cool_st pack_st or1_st - station
    ac1 - autoclave
    or1 - or_room
  )

  (:init
    (batch-at b1 intake)
    (batch-dirty b1)
    (batch-available b1)

    ;; Station connectivity — proper pipeline order
    (connected intake decontam_st)
    (connected decontam_st wash_st)
    (connected wash_st sterilize_st)
    (connected sterilize_st cool_st)
    (connected cool_st pack_st)
    (connected pack_st or1_st)

    ;; Station types — each action can ONLY happen at its designated station
    (is-decontam-station decontam_st)
    (is-wash-station wash_st)
    (is-sterilize-station sterilize_st)
    (is-cool-station cool_st)
    (is-pack-station pack_st)

    ;; Transfer times
    (= (transfer-time intake decontam_st) 1)
    (= (transfer-time decontam_st wash_st) 1)
    (= (transfer-time wash_st sterilize_st) 1)
    (= (transfer-time sterilize_st cool_st) 1)
    (= (transfer-time cool_st pack_st) 1)
    (= (transfer-time pack_st or1_st) 2)

    ;; Bounded durations
    (= (decontaminate-min b1) 3) (= (decontaminate-max b1) 8)
    (= (wash-min b1) 2)          (= (wash-max b1) 6)
    (= (sterilize-min b1) 5)     (= (sterilize-max b1) 12)
    (= (cool-min b1) 3)
    (= (pack-min b1) 1)          (= (pack-max b1) 4)

    ;; Autoclave
    (autoclave-free ac1)
    (autoclave-at ac1 sterilize_st)

    ;; OR1 window
    (or-window-open or1)
    (or-needs-batch or1 b1)
    (or-at or1 or1_st)
    (at 30 (not (or-window-open or1)))
  )

  (:goal (batch-delivered b1))
)
