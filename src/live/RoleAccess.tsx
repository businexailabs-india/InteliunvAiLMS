import { useState } from "react";
import { Btn, Notice, Title, send, useAction } from "./shared";

/** Assigns a stored institution role. The API refuses super-admin grants and self-promotion. */
export default function RoleAccess() {
  const [userId, setUserId] = useState("");
  const [roleCode, setRoleCode] = useState("teacher");
  const action = useAction();

  return (
    <div className="page-stack">
      <Title
        tag="ROLE ASSIGNMENT"
        title="Roles"
        copy="Assign a role that already exists in this institution. Platform super admin cannot be granted from here unless you already hold that role."
      />
      <section className="card form-grid">
        <label>
          User id
          <input value={userId} onChange={(event) => setUserId(event.target.value)} placeholder="User id from this institution" />
        </label>
        <label>
          Role
          <select value={roleCode} onChange={(event) => setRoleCode(event.target.value)}>
            {["teacher", "student", "coordinator", "parent_guardian", "corporate_trainer", "corporate_hr", "finance_admin", "content_creator", "content_reviewer", "support_officer", "compliance_officer", "principal_academic_director", "institution_admin"].map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
        <Btn
          variant="primary"
          disabled={action.busy || userId.trim().length < 8}
          onClick={() =>
            action.run(async () => {
              await send("POST", "/api/v1/role-assignments", { user_id: userId.trim(), role_code: roleCode });
              return `Assigned ${roleCode}`;
            })
          }
        >
          {action.busy ? "Saving..." : "Assign role"}
        </Btn>
      </section>
      <Notice text={action.ok} tone="success" />
      <Notice text={action.fail} tone="danger" />
    </div>
  );
}
