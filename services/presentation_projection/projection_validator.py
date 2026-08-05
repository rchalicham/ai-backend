class ProjectionValidator:
    def validate(self, projection):
        errors = []
        if not projection.metadata.document_family: errors.append("missing_document_family")
        if not projection.fields: errors.append("missing_projection_fields")
        return tuple(errors)

