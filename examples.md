# Examples

## Practical start
In Jakarta/JAX-RS and Spring REST apps, annotations are metadata that declare
how classes and methods are exposed as API endpoints and how requests are
handled.  They control **visibility/routing** (e.g., `@Path`, `@GET`, `@POST`
in JAX-RS or `@RequestMapping`, `@GetMapping` in Spring), so the framework
knows which URL and HTTP verb maps to which method.  They also define
request/response behavior (`@Consumes`, `@Produces`, `@RequestBody`,
`@PathParam`, etc.), making serialization and parameter binding explicit.  For
security/RBAC, annotations like `@RolesAllowed`, `@PermitAll`, `@DenyAll`, or
Spring’s `@PreAuthorize`/`@Secured` enforce who can call an endpoint based on
roles/permissions, usually before method logic runs.

### Create a map
```bash
$ python jmapq.py ./_app/
```

### Show imports
```bash
$ jq -r '.units[].imports?[]' map.json | sort -u
com.atlassian.activeobjects.external.ActiveObjects
com.atlassian.activeobjects.external.ActiveObjectsUpgradeTask
com.atlassian.confluence.api.service.accessmode.ReadOnlyAccessAllowed
...
com.atlassian.migration.app.AccessScope
com.atlassian.migration.app.ServerAppCustomField
com.atlassian.plugin.Application
com.atlassian.plugin.ModuleDescriptor
com.atlassian.plugin.module.ModuleFactory
com.atlassian.plugin.osgi.external.ListableModuleDescriptorFactory
com.atlassian.plugin.Plugin
...
com.atlassian.templaterenderer.TemplateRenderer
com.atlassian.upm.api.license.entity.PluginLicense
com.atlassian.upm.api.license.PluginLicenseManager
com.fasterxml.jackson.annotation.JsonAlias
com.fasterxml.jackson.annotation.JsonIgnoreProperties
com.fasterxml.jackson.annotation.JsonInclude
com.fasterxml.jackson.databind.JsonDeserializer
com.fasterxml.jackson.databind.JsonNode
...
com.google.gson.annotations.Expose
com.google.gson.annotations.JsonAdapter
com.google.gson.annotations.Since
com.google.gson.annotations.Until
com.google.gson.ExclusionStrategy
com.google.gson.FieldAttributes
com.google.gson.Gson
...
com.sample.atlassian.common.config.CommonJavaConfig
com.sample.atlassian.common.config.Jersey1Condition
com.sample.atlassian.common.config.Jersey1Config
com.sample.atlassian.common.config.Jersey2Condition
com.sample.atlassian.common.config.Jersey2Config
com.sample.atlassian.common.server.action.CustomChartsActionSupport
com.sample.atlassian.common.server.ao.dao.GenericDao
com.sample.atlassian.common.server.ao.dao.impl.PermissionDaoImpl
com.sample.atlassian.common.server.ao.dao.PermissionDao
com.sample.atlassian.common.server.ao.dao.TemplateCategoryDao
com.sample.atlassian.common.server.ao.dao.TemplateDao
...
com.opensymphony.util.TextUtils
jakarta.annotation.Nonnull
jakarta.annotation.Nullable
jakarta.annotation.Priority
jakarta.inject.Inject
jakarta.inject.Named
jakarta.inject.Singleton
jakarta.servlet.DispatcherType
jakarta.servlet.Filter
jakarta.servlet.FilterChain
jakarta.servlet.FilterConfig
jakarta.servlet.http.Cookie
jakarta.servlet.http.HttpServletRequest
jakarta.servlet.http.HttpServletResponse
jakarta.servlet.ServletException
jakarta.servlet.ServletRequest
jakarta.servlet.ServletResponse
jakarta.transaction.Transactional
jakarta.ws.rs.Consumes
...
jakarta.ws.rs.PUT
jakarta.ws.rs.QueryParam
jakarta.xml.bind.annotation.XmlAttribute
jakarta.xml.bind.annotation.XmlElement
jakarta.xml.bind.annotation.XmlEnum
jakarta.xml.bind.annotation.XmlEnumValue
jakarta.xml.bind.annotation.XmlRootElement
jakarta.xml.bind.annotation.XmlTransient
...
java.sql.Date
java.sql.Time
java.sql.Timestamp
...
org.codehaus.jackson.map.DeserializationContext
org.codehaus.jackson.map.JsonDeserializer
org.eclipse.gemini.blueprint.service.importer.support.OsgiServiceCollectionProxyFactoryBean
org.eclipse.gemini.blueprint.service.importer.support.OsgiServiceProxyFactoryBean
...
org.osgi.framework.Bundle
org.osgi.framework.BundleContext
org.osgi.framework.FrameworkUtil
org.osgi.framework.ServiceReference
org.osgi.framework.ServiceRegistration
...
org.semver4j.internal.Tokenizers
org.semver4j.internal.Utils
org.semver4j.Semver
org.semver4j.SemverException
org.slf4j.Logger
org.slf4j.LoggerFactory
...
org.springframework.beans.BeansException
org.springframework.beans.factory.annotation.Qualifier
org.springframework.beans.factory.BeanInitializationException
org.springframework.beans.factory.config.AutowireCapableBeanFactory
org.springframework.beans.factory.DisposableBean
```

### List annotations

```bash
$ python jmapq.py --query annotations
AllowedFeature
AllowedRole
AnonymousAllowed
AnonymousSiteAccess
Bean
BrowserSecurity
CanIgnoreReturnValue
ComponentScan
Conditional
Configuration
Consumes
Context
CookieParam
DELETE
DependsOn
Deprecated
GET
Import
InlineMe
JiraApi
JsonAlias
JsonIgnoreProperties
JsonInclude
JsonProperty
JsonSerialize
Named
Nonnull
NullMarked
Nullable
Override
POST
PUT
ParametersAreNonnullByDefault
Path
PathParam
Priority
Produces
Provider
PublicApi
QueryParam
ReadOnlyAccessAllowed
ReadOnlyTransaction
RequiredUIVersion
ReturnValuesAreNonnullByDefault
Singleton
SupportedMethods
Transactional
Transient
UnrestrictedAccess
XmlElement
XmlRootElement
XmlTransient
com.atlassian.plugins.rest.api.security.annotation.UnrestrictedAccess
com.fasterxml.jackson.annotation.JsonIgnoreProperties
com.fasterxml.jackson.annotation.JsonProperty
```

### Check which types of data application accept and produce

```bash
$ python jmapq.py --query media-types
{
  "Consumes": [
    "application/json"
  ],
  "Produces": [
    "application/json"
  ]
}
```

List of imports may help to easily pick gadgets @
[ysoserial](https://github.com/frohoff/ysoserial)

Based on gathered information we can concur:
- This is `jakarta` application. Probably a confluence plugin.
- It only consumes and produces `application/json` (at least no obvious places
  to look for XXE).
- It has `Role` annotations meaning there's at least an attempt to implement
  proper RBAC.

### Explore endpoints

Show information for single (first) REST endpoint:

```bash
$ python jmapq.py --query endpoints | jq '.[0]'
{
  "method": "GET",
  "base": "/external-data/teams/",
  "path": "",
  "uri_path": "/external-data/teams/",
  "parameters": {
    "httpServletRequest": {
      "type": "HttpServletRequest",
      "annotations": [
        "Context"
      ]
    },
    "page": {
      "type": "<jast._jast.Int object at 0x7fe090ffe5f0>",
      "annotations": [
        "QueryParam"
      ]
    }
  }
}
```

Show information for every REST endpoint as a table:

```bash
$ python jmapq.py --query endpoints --plain
```
| Method | Endpoint  | Parameters |
|---|---|---|
| GET    | /external-data/teams/                                           | Context: httpServletRequest @ QueryParam: page                                                                       |
| GET    | /external-data/xray/statuses                                    | Context: httpServletRequest                                                                                          |
| GET    | /settings/permissions/                                          |                                                                                                                      |
| POST   | /settings/permissions/                                          | Param: permission                                                                                                    |
| GET    | /settings/permissions/current-user                              | QueryParam: type                                                                                                     |
| DELETE | /settings/permissions/{id}                                      | PathParam: permissionId                                                                                              |
| ...    | ... | ... |
| GET    | /app/                                                           | QueryParam: type @ QueryParam: mode                                                                                  |
| GET    | /content/render/dashboard-item/{type}                           | PathParam: type @ QueryParam: mode @ QueryParam: dashboardId @ QueryParam: dashboardItemId                           |
| POST   | /logging/                                                       | Param: error                                                                                                         |

## Customization

Adding a custom query as easy as adding a predefined `jq` query into a python variable:
```python
QUERY_ANONYMOUS='''
[
  .units[]
  | .path as $path
  | (
      (.classes[]? | select((.annotations // []) | any(.name == "AnonymousAllowed")) | $path),
      (.classes[]? | .methods[]? | select((.annotations // []) | any(.name == "AnonymousAllowed")) | $path)
    )
]
| unique[]
'''.strip()
BUILTIN_QUERIES: dict[str, tuple[str, bool]] = {
    "annotations": (QUERY_ALL_ANNOTATIONS, True),
    # ...
    "files-with-anon": (QUERY_ANONYMOUS, True),
}
```

Show filepath of each file that has a class or method with `AnonymousAllowed` annotation.

```
$ python jmapq.py --query files-with-anon
```
