# Rules

Soft project rules and conventions — advisory, not invariants.
Depart from one knowingly and say why; don't violate one by accident.


## 2026-07-14T00:14:05-05:00 _(cli)_

Never let a caller's error be swallowed into a silent no-op. If a flag/path/precondition is wrong, exit nonzero with a message — orchestrators redirect stderr and '|| true' the call, so a silent failure is indistinguishable from success and can stay dead for months.
