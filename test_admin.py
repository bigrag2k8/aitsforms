"""Admin console + auth-isolation tests."""
import json
import urllib.request
import urllib.error
from http.cookiejar import CookieJar

BASE = "http://127.0.0.1:8000"


class Client:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(BASE + path, data=data, method=method)
        if data:
            r.add_header("Content-Type", "application/json")
        try:
            resp = self.opener.open(r)
            return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def get(self, p): return self.req("GET", p)
    def post(self, p, b=None): return self.req("POST", p, b)


def show(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
    return ok


results = []

# Admin login
admin = Client()
s, _ = admin.post("/api/admin/login", {"email": "owner@titleapp.example", "password": "ownerpw123"})
results.append(show("admin login -> 200", s == 200))
results.append(show("admin bad password -> 401",
                    Client().post("/api/admin/login", {"email": "owner@titleapp.example", "password": "x"})[0] == 401))

# Business user (Alice)
alice = Client()
alice.post("/api/login", {"email": "alice@buckeye.example", "password": "alicepw123"})

# Cross-domain isolation
results.append(show("admin cookie CANNOT hit /api/jobs -> 401", admin.get("/api/jobs")[0] == 401))
results.append(show("user cookie CANNOT hit /api/admin/businesses -> 401", alice.get("/api/admin/businesses")[0] == 401))
results.append(show("anon CANNOT hit /api/admin/businesses -> 401", Client().get("/api/admin/businesses")[0] == 401))

# Admin can list businesses
s, b = admin.get("/api/admin/businesses")
biz = json.loads(b)
results.append(show("admin lists existing businesses", len(biz) >= 2 and all("user_count" in x for x in biz)))

# Admin creates a business + user
s, b = admin.post("/api/admin/businesses", {"name": "Test Provisioned Title LLC"})
new_biz_id = json.loads(b)["id"]
results.append(show("admin create business -> id", bool(new_biz_id)))

s, b = admin.post("/api/admin/users", {"business_id": new_biz_id, "email": "dave@provisioned.example", "name": "Dave Davis"})
created = json.loads(b)
results.append(show("admin create user -> returns password", bool(created.get("password"))))

# The newly created user can log into the main app
dave = Client()
s, _ = dave.post("/api/login", {"email": "dave@provisioned.example", "password": created["password"]})
results.append(show("provisioned user can log in", s == 200))

# Admin deactivates the new business -> Dave blocked
admin.post(f"/api/admin/businesses/{new_biz_id}/active", {"active": False})
results.append(show("deactivated business blocks user (/me -> 401)", dave.get("/api/me")[0] == 401))
results.append(show("deactivated business blocks re-login (-> 403)",
                    Client().post("/api/login", {"email": "dave@provisioned.example", "password": created["password"]})[0] == 403))
admin.post(f"/api/admin/businesses/{new_biz_id}/active", {"active": True})

# Admin resets Dave's password -> new password works, old fails
s, b = admin.post(f"/api/admin/users/{created['id']}/reset-password", {})
newpw = json.loads(b)["password"]
results.append(show("reset: new password logs in",
                    Client().post("/api/login", {"email": "dave@provisioned.example", "password": newpw})[0] == 200))
results.append(show("reset: old password rejected",
                    Client().post("/api/login", {"email": "dave@provisioned.example", "password": created["password"]})[0] == 401))

# Admin logout
results.append(show("admin logout -> 200", admin.post("/api/admin/logout")[0] == 200))
results.append(show("admin /me after logout -> 401", admin.get("/api/admin/me")[0] == 401))

print(f"\n{sum(results)}/{len(results)} checks passed")
