def create_aura():
    from aura_core.bootstrap.bootstrap import create_aura as _create_aura

    return _create_aura()


__all__ = ["create_aura"]
