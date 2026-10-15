"""Ground-truth benchmark: a flawed fixture app plus an executable spec.

A finding is an exploit script. `verify.run_script` runs it against a fresh
NoteShare instance and `spec.check` decides, from the request log alone,
whether a stated claim was actually violated. Nothing here calls an LLM.
"""
