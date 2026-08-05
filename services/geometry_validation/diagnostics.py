def observation_diagnostics(result):
    return {key:{"measurement":value.measurement,"confidence":value.confidence,"reliable":value.reliable,
                 "reason":value.reason,"diagnostics":dict(value.diagnostics)} for key,value in result.observations.items()}
