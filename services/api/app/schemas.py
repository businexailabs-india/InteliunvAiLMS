from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InstitutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    status: str
    tenant_type: str = "education"
    branding: dict
    synthetic: bool = True


class InstitutionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    branding: dict | None = None


class DemoLoginRequest(BaseModel):
    email: str
    password: str
    institution_slug: str | None = None


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=2, max_length=80)
    institution_name: str = Field(min_length=2, max_length=200)
    create_institution: bool = False


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    display_name: str
    email: str | None
    institution_id: UUID
    institution_name: str
    institution_slug: str
    roles: list[str]
    auth_mode: str
    synthetic: bool = True


class CourseCreate(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    level: str = "beginner"
    description: str = ""


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    institution_id: UUID
    title: str
    level: str
    status: str
    description: str
    synthetic: bool = True


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    course_id: UUID
    status: str
    progress_pct: int


class LessonCompleteRequest(BaseModel):
    lesson_id: UUID


class AttendanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    course_id: UUID
    sessions_total: int
    sessions_present: int
    status: str


class AssessmentCreate(BaseModel):
    course_id: UUID
    title: str
    max_score: int = 100
    proctored: bool = False
    questions: list[dict] = Field(default_factory=list)
    integrity: dict = Field(default_factory=dict)


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    title: str
    max_score: int
    proctored: bool
    status: str
    questions: list
    integrity: dict = Field(default_factory=dict)
    checks: dict = Field(default_factory=dict)


class AttemptSubmit(BaseModel):
    answers: list[dict] = Field(default_factory=list)


class AttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assessment_id: UUID
    student_id: UUID
    score: int | None
    status: str
    answers: list
    published: bool


class ScoreAdjustmentRequest(BaseModel):
    revised_score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=8)


class ScorecardCreate(BaseModel):
    course_id: UUID
    payload: dict = Field(default_factory=dict)


class AssignmentCreate(BaseModel):
    course_id: UUID
    title: str = Field(min_length=3, max_length=240)
    instructions: str = ""
    max_score: int = Field(default=100, ge=1, le=1000)
    due_at: datetime | None = None


class SubmissionCreate(BaseModel):
    body: str


class GamePlayRequest(BaseModel):
    game_type: str
    correct: int = 0
    total: int = 10
    elapsed_seconds: int = 30
    source_event_id: str


class GamePlayResponse(BaseModel):
    xp_awarded: int
    total_xp: int
    rank: int = 0
    leaderboard: list[dict]


class AiQuotaUpdate(BaseModel):
    monthly_token_quota: int = Field(ge=0, le=100_000_000)


class QuestionBankCreate(BaseModel):
    course_id: UUID | None = None
    qtype: str = "mcq"
    prompt: str = Field(min_length=3)
    options: list[str] = Field(default_factory=list)
    answer: str | None = None
    points: int = Field(default=1, ge=1, le=100)
    difficulty: str = "medium"


class QuestionBankResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID | None
    qtype: str
    prompt: str
    options: list
    answer: str | None = None
    points: int
    difficulty: str
    status: str
    synthetic: bool = True


class AssessmentFromBank(BaseModel):
    course_id: UUID
    title: str = Field(min_length=2)
    item_ids: list[UUID] = Field(min_length=1)
    proctored: bool = False


class CohortMemberAdd(BaseModel):
    user_ids: list[UUID] = Field(min_length=1)


class AiAskRequest(BaseModel):
    message: str
    course_id: UUID | None = None
    conversation_id: UUID | None = None
    feature: str = "study_buddy"


class AiAskResponse(BaseModel):
    conversation_id: UUID
    reply: str
    citations: list[dict]
    provider: str
    tokens_in: int
    tokens_out: int
    estimated_cost: float
    mock: bool


class CopilotRequest(BaseModel):
    task: str
    course_id: UUID | None = None
    topic: str = ""


class AdaptiveResponse(BaseModel):
    skill_gaps: list[dict]
    recommendations: list[str]
    mock: bool = True


class SuccessInsight(BaseModel):
    student_id: UUID
    attendance_pct: float
    assessment_avg: float | None
    risk_level: str
    indicators: list[str]
    interventions: list[str]
    advisory: bool = True


class ProctorStartRequest(BaseModel):
    assessment_id: UUID
    consent: bool
    camera_ready: bool = False
    microphone_ready: bool = False
    identity_confirmed: bool = False


class PracticeAnswer(BaseModel):
    question_id: str
    value: str = ""


class PracticeSubmit(BaseModel):
    game: str
    course_id: UUID | None = None
    answers: list[PracticeAnswer] = Field(min_length=1)
    elapsed_seconds: int = Field(default=30, ge=0, le=3600)
    source_event_id: str = Field(min_length=8, max_length=120)


class ProctorReviewRequest(BaseModel):
    decision: str
    notes: str = ""


class CohortCreate(BaseModel):
    name: str
    course_id: UUID | None = None


class ScheduledClassCreate(BaseModel):
    course_id: UUID
    title: str = Field(min_length=3, max_length=240)
    starts_at: datetime
    duration_minutes: int = Field(default=45, ge=15, le=240)
    timezone: str = Field(min_length=1, max_length=80)


class StudySessionWrite(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    starts_at: datetime
    timezone: str = Field(min_length=1, max_length=80)


class DashboardResponse(BaseModel):
    role: str
    metrics: dict
    courses: list[CourseResponse]
    notifications: list[dict]
    generated_at: datetime
