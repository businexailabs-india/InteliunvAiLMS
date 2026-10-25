import { useEffect, useState } from "react";
import { apiFetch } from "../api/client";
import { Badge, Btn, Empty, Loading, Notice, Title, send, useAction, useApi, useCoursePicker } from "./shared";

type Question = { id: string; prompt: string; options: string[] };
type Deck = { questions: Question[] };
type Feedback = { question_id: string; prompt: string; correct: boolean; expected: string; submitted: string };
type Result = { correct: number; total: number; score_pct: number; xp_awarded: number; total_xp: number; rank: number; badge: string | null; feedback: Feedback[] };
type Standing = { total_xp: number; rank: number; recent?: { game_type: string; xp: number; details: { score_pct?: number; badge?: string | null } }[] };

export function PracticeGame({ game, title, navigate }: { game: "quiz" | "quick_quest"; title: string; navigate: (module: string, sub?: string) => void }) {
  const { courseId, picker } = useCoursePicker();
  const standing = useApi<Standing>("/api/v1/gamification");
  const [phase, setPhase] = useState<"intro" | "play" | "result">("intro");
  const [deck, setDeck] = useState<Question[]>([]);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [seconds, setSeconds] = useState(0);
  const [left, setLeft] = useState(15);
  const [result, setResult] = useState<Result | null>(null);
  const action = useAction();
  const timed = game === "quick_quest";

  useEffect(() => {
    if (phase !== "play" || !timed) return;
    setLeft(15);
    const timer = window.setInterval(() => setLeft((value) => (value > 0 ? value - 1 : 0)), 1000);
    return () => window.clearInterval(timer);
  }, [phase, index, timed]);

  useEffect(() => {
    if (phase !== "play") return;
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [phase]);

  const start = () =>
    action.run(async () => {
      const path = `/api/v1/practice-deck?game=${game}${courseId ? `&course_id=${courseId}` : ""}`;
      const deckResponse = await apiFetch<Deck>(path);
      if (!deckResponse.questions.length) return "This course has no playable questions yet.";
      setDeck(deckResponse.questions);
      setIndex(0);
      setAnswers({});
      setSeconds(0);
      setPhase("play");
      return `${deckResponse.questions.length} questions ready.`;
    });

  const finish = (finalAnswers: Record<string, string>) =>
    action.run(async () => {
      const saved = await send<Result>("POST", "/api/v1/practice-deck/submit", {
        game,
        course_id: courseId || null,
        elapsed_seconds: seconds,
        source_event_id: crypto.randomUUID(),
        answers: deck.map((question) => ({ question_id: question.id, value: finalAnswers[question.id] ?? "" })),
      });
      setResult(saved);
      setPhase("result");
      standing.reload();
      return `Saved. ${saved.correct} of ${saved.total} correct.`;
    });

  const choose = (value: string) => {
    const question = deck[index];
    if (!question) return;
    const next = { ...answers, [question.id]: value };
    setAnswers(next);
  };

  const advance = () => {
    if (index < deck.length - 1) setIndex(index + 1);
    else finish(answers);
  };

  if (phase === "result" && result) {
    return (
      <div className="page-stack">
        <Title tag="RESULT SAVED" title={title} copy="Points and the score are stored for this account and course." actions={<Btn onClick={() => navigate("Gamification", "Game Library")}>Back to games</Btn>} />
        <section className="card">
          <h2>{result.score_pct}%</h2>
          <p>{result.correct} of {result.total} correct · {result.xp_awarded} XP this session · {result.total_xp} XP total · rank {result.rank}</p>
          {result.badge ? <Badge tone="success">{result.badge}</Badge> : <Badge>No badge this round. 80% earns the accuracy badge.</Badge>}
          {result.feedback.map((item) => (
            <div className="scope-row" key={item.question_id}>
              <span><strong>{item.prompt}</strong><small>{item.correct ? "Correct" : `Answer: ${item.expected}`}</small></span>
              <Badge tone={item.correct ? "success" : "warning"}>{item.correct ? "CORRECT" : "INCORRECT"}</Badge>
            </div>
          ))}
          <div className="panel-actions"><Btn variant="primary" onClick={() => setPhase("intro")}>Play again</Btn></div>
        </section>
      </div>
    );
  }

  if (phase === "play") {
    const question = deck[index];
    if (!question) return <Empty title="No questions in this deck" />;
    return (
      <div className="page-stack">
        <Title tag={`QUESTION ${index + 1} OF ${deck.length}`} title={question.prompt} copy={timed ? `${left}s left on this question` : "Choose one answer, then continue."} />
        <Notice text={action.fail} tone="danger" />
        <section className="card">
          <div className="live-answer-grid">
            {question.options.map((option) => (
              <button className={answers[question.id] === option ? "selected" : ""} key={option} onClick={() => choose(option)}>
                <strong>{option}</strong>
              </button>
            ))}
          </div>
          <div className="panel-actions">
            <Btn variant="primary" disabled={action.busy || (!answers[question.id] && !(timed && left === 0))} onClick={advance}>{timed && left === 0 ? "Time is up" : index === deck.length - 1 ? "Finish and save" : "Next question"}</Btn>
          </div>
        </section>
      </div>
    );
  }

  const mine = (standing.data?.recent ?? []).filter((row) => row.game_type === game);
  return (
    <div className="page-stack">
      <Title tag={game === "quiz" ? "QUIZ CHALLENGE" : "QUICK QUEST"} title={title} copy={game === "quiz" ? "Five questions, scored and saved against your account." : "Answer before the timer ends. Accuracy and speed award points."} />
      <div className="card form-grid">{picker}</div>
      <Notice text={action.fail} tone="danger" />
      {standing.loading ? <Loading what="progress" /> : null}
      <section className="card">
        <p>{standing.data ? `${standing.data.total_xp} XP · rank ${standing.data.rank}` : "Sign in to save points."}</p>
        <p>Instructions: pick the course, answer every question, and submit. A score of 80% or higher awards the accuracy badge. Progress remains after you sign out.</p>
        {mine.slice(0, 3).map((row, position) => <div className="scope-row" key={`${row.game_type}-${position}`}><span><strong>Previous score {row.details?.score_pct ?? "saved"}%</strong><small>{row.xp} XP{row.details?.badge ? ` · ${row.details.badge}` : ""}</small></span></div>)}
        <Btn variant="primary" disabled={action.busy} onClick={start}>{action.busy ? "Loading..." : "Start"}</Btn>
      </section>
    </div>
  );
}
