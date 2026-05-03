(define (problem hospital-p02-two-batches)
  (:domain hospital-sterilization)

  (:objects
    b1 b2 - batch
    intake decontam_st wash_st sterilize_st cool_st pack_st or1_st or2_st - station
    ac1 - autoclave
    or1 or2 - or_room
  )

  (:init
    (batch-at b1 intake) (batch-dirty b1) (batch-available b1)
    (batch-at b2 intake) (batch-dirty b2) (batch-available b2)

    ;; Station connectivity
    (connected intake decontam_st)
    (connected decontam_st wash_st)
    (connected wash_st sterilize_st)
    (connected sterilize_st cool_st)
    (connected cool_st pack_st)
    (connected pack_st or1_st)
    (connected pack_st or2_st)

    ;; Station types — enforce correct processing locations
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

    ;; Autoclave
    (autoclave-free ac1)
    (autoclave-at ac1 sterilize_st)

    ;; OR1 — for b1
    (or-window-open or1)
    (or-needs-batch or1 b1)
    (or-at or1 or1_st)
    (at 36 (not (or-window-open or1)))

    ;; OR2 — for b2 (and b1 fallback)
    (or-at or2 or2_st)
    (or-needs-batch or2 b2)
    (or-needs-batch or2 b1)
    (at 10 (or-window-open or2))
    (at 46 (not (or-window-open or2)))
  )

  (:goal
    (and
      (batch-delivered b1)
      (batch-delivered b2)
    )
  )
)
