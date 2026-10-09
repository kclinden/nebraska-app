def specification():
    paths = {}

    def operation(path, method, summary, authenticated=False, properties=None, required=None, response="200"):
        definition = {
            "summary": summary,
            "operationId": method + "_" + path.strip("/").replace("/", "_").replace("{", "").replace("}", ""),
            "responses": {response: {"description": "Success"}, "400": {"description": "Invalid input"}},
        }
        if authenticated:
            definition["security"] = [{"sessionCookie": []}]
            definition["responses"]["401"] = {"description": "Login required"}
        if "{id}" in path:
            definition["parameters"] = [{"name": "id", "in": "path", "required": True,
                                          "schema": {"type": "integer" if "/games/" in path else "string"}}]
            definition["responses"]["404"] = {"description": "Not found"}
        if properties:
            schema = {"type": "object", "properties": properties}
            if required:
                schema["required"] = required
            definition["requestBody"] = {"required": True, "content": {"application/json": {"schema": {
                **schema,
            }}}}
        paths.setdefault(path, {})[method] = definition

    operation("/api/v1/session", "get", "Obtain CSRF token and session status; retain session cookie")
    operation("/api/v1/session", "post", "Log in using X-CSRF-Token from GET /api/v1/session", properties={
        "username": {"type": "string"}, "password": {"type": "string", "format": "password"},
    }, required=["username", "password"])
    operation("/api/v1/session", "delete", "Log out using X-CSRF-Token", response="204")
    for method in ("post", "delete"):
        paths["/api/v1/session"][method]["parameters"] = [{
            "name": "X-CSRF-Token", "in": "header", "required": True, "schema": {"type": "string"},
        }]
    operation("/api/v1/games", "get", "List the schedule")
    operation("/api/v1/games/{id}/stats", "get", "Get baked-in final scores and stats")
    operation("/api/v1/players", "get", "List players; optional name search")
    paths["/api/v1/players"]["get"]["parameters"] = [{"name": "q", "in": "query", "schema": {"type": "string"}}]
    operation("/api/v1/players", "post", "Add a player (intentional missing admin-role check)", True, {
        "JerseyNumber": {"type": "integer", "minimum": 0, "maximum": 999},
        "Name": {"type": "string"}, "Position": {"type": "string"},
    }, ["JerseyNumber", "Name", "Position"], "201")
    operation("/api/v1/players/{id}", "patch", "Update position (intentional missing admin-role check)", True,
              {"Position": {"type": "string"}}, ["Position"])
    operation("/api/v1/players/{id}", "delete", "Remove player (intentional missing admin-role check)", True, response="204")
    operation("/api/v1/users/me", "get", "Get current user (includes synthetic internal metadata)", True)
    operation("/api/v1/users/me", "patch", "Update profile (intentional role mass assignment)", True, {
        "Role": {"type": "string", "enum": ["viewer", "admin"]},
        "Department": {"type": "string"}, "InternalNote": {"type": "string"},
    })
    operation("/api/v1/reports", "get", "List reports owned by current user", True)
    operation("/api/v1/reports/{id}", "get", "Get private report (intentional missing ownership check)", True)
    return {
        "openapi": "3.0.3", "info": {"title": "Nebraska Security Lab API", "version": "1.0.0",
        "description": "Intentionally vulnerable security testing application. Synthetic data only."},
        "servers": [{"url": "/"}], "paths": paths,
        "components": {"securitySchemes": {"sessionCookie": {"type": "apiKey", "in": "cookie", "name": "session"}}},
    }