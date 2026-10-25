import { useEffect, useState } from "react";
import { Badge, Btn, Empty, ErrorBox, Loading, Notice, Title, send, useAction, useApi } from "./shared";

type Checks = { camera?: string; microphone?: string; identity?: string };
type Question = { id?: string; prompt?: string; options?: string[]; type?: string };
type Exam = { id: string; title: string; proctored: boolean; questions: Question[]; checks?: Checks };
type Graded = { question_id: string; correct: boolean | null; expected?: string; awarded: number | null };
type Attempt = { score: number | null; status: string; answers: Graded[] };

async function deviceReady(kind: "camera" | "microphone") {
  if (!navigator.mediaDevices?.getUserMedia) return { ok: false, label: "" };
  try {
    const stream = await navigator.mediaDevices.getUserMedia(kind === "camera" ? { video: true } : { audio: true });
    const label = stream.getTracks()[0]?.label || kind;
    stream.getTracks().forEach((track) => track.stop());
    return { ok: true, label };
  } catch {
    return { ok: false, label: "" };
  }
}

function rulesFor(exam: Exam): Required<Checks> {
  const checks = exam.checks ?? {};
  if (exam.proctored && !checks.camera && !checks.microphone && !checks.identity) {
    return { camera: "required", microphone: "required", identity: "required" };
  }
  return {
    camera: checks.camera ?? "off",
    microphone: checks.microphone ?? "off",
    identity: checks.identity ?? "off",
  };
}

export function StudentExamCenter({ navigate }: { navigate: (module: string, sub?: string, detail?: string) => void }) {
  const exams = useApi<Exam[]>("/api/v1/assessments");
  const [examId, setExamId] = useState("");
  const [phase, setPhase] = useState<"list" | "checks" | "exam" | "result">("list");
  const [camera, setCamera] = useState<"idle" | "pass" | "fail">("idle");
  const [microphone, setMicrophone] = useState<"idle" | "pass" | "fail">("idle");
  const [identity, setIdentity] = useState("");
  const [cameraLabel, setCameraLabel] = useState("");
  const [microphoneLabel, setMicrophoneLabel] = useState("");
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<Attempt | null>(null);
  const action = useAction();
  const exam = (exams.data ?? []).find((item) => item.id === examId) ?? null;
  const rules = exam ? rulesFor(exam) : null;
  const questions = exam?.questions ?? [];

  useEffect(() => {
    setCamera("idle");
    setMicrophone("idle");
    setIdentity("");
    setCameraLabel("");
    setMicrophoneLabel("");
    setIndex(0);
    setAnswers({});
    setResult(null);
    setPhase("list");
  }, [examId]);

  const blocked = (name: keyof Checks) => {
    if (!rules || rules[name] !== "required") return false;
    if (name === "camera") return camera !== "pass";
    if (name === "microphone") return microphone !== "pass";
    return identity.trim().length < 2;
  };
  const canStart = exam && !blocked("camera") && !blocked("microphone") && !blocked("identity");

  const runDevices = async () => {
    if (!rules) return;
    if (rules.camera !== "off") {
      const cameraCheck = await deviceReady("camera");
      setCamera(cameraCheck.ok ? "pass" : "fail");
      setCameraLabel(cameraCheck.label);
    }
    if (rules.microphone !== "off") {
      const microphoneCheck = await deviceReady("microphone");
      setMicrophone(microphoneCheck.ok ? "pass" : "fail");
      setMicrophoneLabel(microphoneCheck.label);
    }
  };

  const begin = () =>
    action.run(async () => {
      if (!exam || !canStart) return "Complete the required checks first.";
      const needsGate = rules && Object.values(rules).some((level) => level === "required");
      if (needsGate) {
        await send("POST", "/api/v1/proctoring/sessions", {
          assessment_id: exam.id,
          consent: true,
          camera_ready: camera === "pass",
          microphone_ready: microphone === "pass",
          camera_label: cameraLabel,
          microphone_label: microphoneLabel,
          identity_confirmed: identity.trim().length > 1,
          identity_name: identity.trim(),
        });
      }
      setPhase("exam");
      return "Checks recorded. The assessment is open.";
    });

  const submit = () =>
    action.run(async () => {
      if (!exam) return;
      const payload = questions.map((question, position) => ({
        question_id: question.id || String(position),
        value: answers[question.id || String(position)] ?? "",
      }));
      const saved = await send<Attempt>("POST", `/api/v1/assessments/${exam.id}/attempts`, { answers: payload });
      setResult(saved);
      setPhase("result");
      return `Submitted. Score ${saved.score ?? 0}%.`;
    });

  if (exams.loading) return <Loading what="assessments" />;
  if (exams.error) return <ErrorBox message={exams.error} onRetry={exams.reload} />;

  if (phase === "result" && exam && result) {
    const graded = result.answers ?? [];
    const correct = graded.filter((item) => item.correct).length;
    return (
      <div className="page-stack">
        <Title tag="ASSESSMENT RESULT" title={exam.title} copy="This result is saved on your account." actions={<Btn onClick={() => navigate("Assessments", "Assessments")}>Back</Btn>} />
        <section className="card">
          <h2>{result.score ?? 0}%</h2>
          <p>{correct} of {graded.length} objective answers were correct.</p>
          {graded.map((item) => (
            <div className="scope-row" key={item.question_id}>
              <span><strong>{item.question_id}</strong><small>{item.correct ? "Correct" : `Expected ${item.expected ?? "review"}`}</small></span>
              <Badge tone={item.correct ? "success" : "warning"}>{item.correct ? "CORRECT" : "INCORRECT"}</Badge>
            </div>
          ))}
        </section>
      </div>
    );
  }

  if (phase === "exam" && exam) {
    const question = questions[index];
    const key = question?.id || String(index);
    return (
      <div className="page-stack">
        <Title tag={`QUESTION ${index + 1} OF ${questions.length}`} title={exam.title} copy="Answer every question, then submit the full attempt." />
        <Notice text={action.fail} tone="danger" />
        {!question ? <Empty title="This assessment has no questions" /> : (
          <section className="card">
            <h2>{question.prompt || "Question"}</h2>
            {(question.options ?? []).length ? (
              <div className="live-answer-grid">
                {question.options!.map((option) => (
                  <button className={answers[key] === option ? "selected" : ""} key={option} onClick={() => setAnswers({ ...answers, [key]: option })}>
                    <strong>{option}</strong>
                  </button>
                ))}
              </div>
            ) : (
              <label>Your answer<input value={answers[key] ?? ""} onChange={(event) => setAnswers({ ...answers, [key]: event.target.value })} /></label>
            )}
            <div className="panel-actions">
              <Btn disabled={index === 0} onClick={() => setIndex(index - 1)}>Previous</Btn>
              {index < questions.length - 1 ? <Btn variant="primary" onClick={() => setIndex(index + 1)}>Next question</Btn> : <Btn variant="primary" disabled={action.busy} onClick={submit}>{action.busy ? "Submitting..." : "Submit assessment"}</Btn>}
            </div>
          </section>
        )}
      </div>
    );
  }

  if (phase === "checks" && exam && rules) {
    const label = (name: keyof Checks, state: string) => rules[name] === "off" ? "Not required" : rules[name] === "optional" ? `Optional · ${state}` : state;
    return (
      <div className="page-stack">
        <Title tag="INTEGRITY CHECKS" title={exam.title} copy="A required check that fails keeps the assessment closed. An optional check does not." actions={<Btn onClick={() => setPhase("list")}>Back</Btn>} />
        <Notice text={action.ok} tone="success" />
        <Notice text={action.fail} tone="danger" />
        <section className="card">
          <div className="scope-row"><span><strong>Camera</strong><small>{label("camera", camera)}</small></span><Badge tone={camera === "pass" ? "success" : camera === "fail" && rules.camera === "required" ? "warning" : "default"}>{rules.camera?.toUpperCase()}</Badge></div>
          <div className="scope-row"><span><strong>Microphone</strong><small>{label("microphone", microphone)}</small></span><Badge tone={microphone === "pass" ? "success" : microphone === "fail" && rules.microphone === "required" ? "warning" : "default"}>{rules.microphone?.toUpperCase()}</Badge></div>
          <label>Identity<input value={identity} onChange={(event) => setIdentity(event.target.value)} placeholder="Type the name on your account" /></label>
          <p>{rules.identity === "required" ? "The name must match your account before the assessment opens." : "Identity is optional for this assessment."}</p>
          <div className="panel-actions">
            <Btn onClick={runDevices}>Run camera and microphone checks</Btn>
            <Btn variant="primary" disabled={!canStart || action.busy} onClick={begin}>{action.busy ? "Checking..." : "Begin assessment"}</Btn>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <Title tag="MY ASSESSMENTS" title="Assessment Center" copy="Open an assessment to see which checks are required before any question is shown." />
      {!(exams.data ?? []).length ? <Empty title="No assessments are published" /> : null}
      {(exams.data ?? []).map((item) => (
        <button className="scope-row card" key={item.id} onClick={() => { setExamId(item.id); setPhase(item.proctored || Object.values(item.checks ?? {}).includes("required") ? "checks" : "exam"); }}>
          <span><strong>{item.title}</strong><small>{item.proctored ? "Proctored · required checks must pass" : "Open · device checks are not required"}</small></span>
          <Badge tone={item.proctored ? "warning" : "success"}>{item.proctored ? "CHECKS REQUIRED" : "START"}</Badge>
        </button>
      ))}
    </div>
  );
}
