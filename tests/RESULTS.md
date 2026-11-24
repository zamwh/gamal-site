# Stock sync — test results

Run on 2026-11-24 against a fresh demo server (real HTTP; a second process writes to the same database, as the shop POS must).

## Server and database (tests/sync_test.py)

- PASS — login owner
- PASS — A  AVAILABLE piece appears on the site
- PASS — B  sell D000001 from the shop (branch 1)
- PASS — C1 sold piece gone from live stock
- PASS — C2 sold piece gone from the site list
- PASS — C3 piece page reports SOLD (sold)
- PASS — C4 second sale of the same piece refused (القطعة D000001 غير متاحة للبيع (sold))
- PASS — C5 terms/accounts refused for sold piece (القطعة غير متاحة حالياً)
- PASS — D  sell D000003 from branch 2 (separate POS process) (INV DS000003)
- PASS — D2 website reflects the branch-2 sale at once
- PASS — E  customer tries to reserve the piece just sold → refused (القطعة غير متاحة حالياً)
- PASS — R1 six simultaneous reservation requests → exactly one accepted (1 accepted, refusals: طلبات كثيرة، حاول بعد قليل | يوجد طلب آخر على هذه القطعة قيد المراجعة)
- PASS — R2 five simultaneous sales of one piece → exactly one invoice ([400, 400, 400, 400, 200])
- PASS — R3 database holds one sale line for D000005 (1)

## Website in a phone browser, 360 px (tests/ui_test.py)

- PASS — A  piece D000002 visible in the collection
- PASS — C  open piece page switches to "sold" within ~20 s, buy buttons gone
- PASS — C2 sold piece no longer in the collection
- PASS — F  connection lost: page keeps working, no crash
- PASS — G  connection back: missed sale applied at once
- PASS — H  360px phone, page home: no sideways scroll
- PASS — H  360px phone, page collections: no sideways scroll
- PASS — H  360px phone, page p-D000004: no sideways scroll
- PASS — H  360px phone, page bride: no sideways scroll
- PASS — H  360px phone, page gold: no sideways scroll
- PASS — H2 no script errors during the whole run

## Not covered

- The Windows desktop POS keeps its own local database (LOCALAPPDATA). Sales made there do NOT reach the website until that POS works on the server database. Covered here: sales from the web admin and from any process on the server database.
