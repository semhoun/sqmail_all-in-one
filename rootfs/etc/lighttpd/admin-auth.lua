-- Enforce the same boundary for PHP, static files and native CGI programs.
local r = lighty.r
r.req_env["REMOTE_USER"] = nil
r.req_env["AUTH_TYPE"] = nil
r.resp_header["Cache-Control"] = "no-store"
r.resp_header["X-Frame-Options"] = "DENY"
r.resp_header["X-Content-Type-Options"] = "nosniff"

local path = r.req_attr["uri.path"]
if path == "/login.php" or path == "/css/style.css" or path == "/css/bootstrap.min.css" then
    return 0
end

local cookies = lighty.c.cookie_tokens(r.req_header["Cookie"] or "")
local token = cookies["__Host-sqmail-admin"] or ""
if #token == 64 and token:match("^[a-f0-9]+$") then
    local file = io.open("/run/sqmail-admin/token-" .. token, "r")
    if file then
        local user, expiry, digest = file:read("*l", "*l", "*l")
        file:close()
        if user and expiry and digest and tonumber(expiry) and tonumber(expiry) > os.time() then
            -- Removing an account or changing its password also revokes its sessions.
            local credentials = io.open("/var/qmail/control/lighttpd-admins.htdigest", "r")
            if credentials then
                local valid = false
                for line in credentials:lines() do
                    if line == user .. ":SQMail AIO Admin:" .. digest then valid = true end
                end
                credentials:close()
                if valid then
                    r.req_env["REMOTE_USER"] = user
                    r.req_env["AUTH_TYPE"] = "Session"
                    return 0
                end
            end
        end
    end
end

-- Never replay an unauthenticated POST after login or accept an external return URL.
r.resp_header["Location"] = "/login.php"
return 303
