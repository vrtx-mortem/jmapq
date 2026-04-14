// 
// Decompiled by Procyon v0.6.0
// 

package com.foo.atlassian.jira.common.rest;

import jakarta.ws.rs.GET;
import com.foo.atlassian.confluence.common.rest.annotation.Role;
import com.foo.atlassian.confluence.common.rest.annotation.AllowedRole;
import com.foo.atlassian.confluence.common.exception.RequestValidationException;
import jakarta.ws.rs.core.Response;
import java.util.concurrent.CompletableFuture;
import jakarta.ws.rs.core.Context;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.Path;
import jakarta.inject.Singleton;
import jakarta.inject.Named;

@Named
@Singleton
@Deprecated
@Path("dashboard/{dashboardId}/items/{dashboardItemId}/toggle-editor")
@Consumes({ "application/json" })
@Produces({ "application/json" })
public class DashboardItemResource
{
    @AllowedRole({ Role.EDITOR, Role.CUSTOM_CHARTS, Role.ISSUE_LIST, Role.SHARED_DASHBOARD, Role.SIMPLE_SEARCH })
    @GET
    @Deprecated
    public CompletableFuture<Response> toggleEditor(@PathParam("dashboardId") final Long dashboardId, @Context final HttpServletRequest request) {
        throw new RequestValidationException("deprecated");
    }
}
