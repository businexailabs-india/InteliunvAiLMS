"""Generate deterministic, fictional multi-tenant LMS JSON fixtures. No real PII."""
import argparse, json, random, uuid
from pathlib import Path

def uid(*parts): return str(uuid.uuid5(uuid.NAMESPACE_DNS, 'inteluniven-demo:' + ':'.join(map(str, parts))))
def write(root, name, rows):
    (root / f'{name}.json').write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')

def generate(root, students):
    rng = random.Random(20261022)
    root.mkdir(parents=True, exist_ok=True)
    roles = [('super_admin',2),('institution_admin',10),('academic_director',5),('coordinator',20),('teacher',100),('student',students),('parent',students//2),('corporate_trainer',20),('hr_manager',10),('finance_admin',5),('content_reviewer',15),('support_officer',5)]
    tenants = [{'id':uid('tenant',i),'slug':f'demo-tenant-{i+1}','name':f'Demo {"Academy" if i<5 else "Corporate Learning"} {i+1}','type':'education' if i<5 else 'corporate'} for i in range(10)]
    users=[]; courses=[]; enrollments=[]; attendance=[]; assessments=[]; attempts=[]; games=[]; ai_requests=[]; proctoring=[]; invoices=[]; parent_links=[]
    for role,count in roles:
        for i in range(count):
            tenant = tenants[i%10]
            users.append({'id':uid('user',role,i),'tenant_id':tenant['id'] if role!='super_admin' else None,'role':role,'display_name':f'Demo {role.replace("_"," ").title()} {i+1:04d}','email':f'demo.{role}.{i+1:04d}@example.invalid','status':'active' if i%17 else 'inactive','synthetic':True})
    course_names=['Python Fundamentals','Data Science','AWS Cloud','Azure Data Engineering','Google Cloud AI','OCI Foundations','SAP BTP','Generative AI','Cybersecurity','Communication Skills']
    for t in tenants:
        for j,name in enumerate(course_names):
            courses.append({'id':uid('course',t['id'],j),'tenant_id':t['id'],'title':name,'level':['beginner','intermediate','advanced'][j%3],'status':'published'})
    for i,u in enumerate(x for x in users if x['role']=='student'):
        t_courses=[c for c in courses if c['tenant_id']==u['tenant_id']]
        for k in range(2):
            c=t_courses[(i+k)%len(t_courses)]
            enrollments.append({'id':uid('enrollment',u['id'],c['id']),'tenant_id':u['tenant_id'],'student_id':u['id'],'course_id':c['id'],'status':['active','completed','dropped'][i%3],'progress_pct':rng.randrange(0,101)})
            attendance.append({'id':uid('attendance',u['id'],c['id']),'tenant_id':u['tenant_id'],'student_id':u['id'],'course_id':c['id'],'sessions_total':20,'sessions_present':rng.randrange(8,21)})
        ai_requests.append({'id':uid('ai',u['id']),'tenant_id':u['tenant_id'],'user_id':u['id'],'feature':'study_buddy','prompt':'Explain a sample course concept','response':'This is a synthetic tutor response for testing.','tokens_in':150,'tokens_out':220,'provider':'mock','synthetic':True})
        games.append({'id':uid('game',u['id']),'tenant_id':u['tenant_id'],'user_id':u['id'],'game_type':['quiz','quick_quest','flashcards'][i%3],'xp':rng.randrange(10,501)})
        if i%4==0: proctoring.append({'id':uid('proctor',u['id']),'tenant_id':u['tenant_id'],'student_id':u['id'],'identity_check':'mock_pass','camera_ready':True,'microphone_ready':True,'event':['none','face_out_of_frame','multiple_voices'][i%3],'decision':'pending_human_review','synthetic':True})
    for t in tenants:
        for j,c in enumerate(x for x in courses if x['tenant_id']==t['id']):
            a={'id':uid('assessment',c['id']),'tenant_id':t['id'],'course_id':c['id'],'title':'Module Knowledge Check','max_score':100,'proctored':j%3==0}
            assessments.append(a)
        invoices.append({'id':uid('invoice',t['id']),'tenant_id':t['id'],'currency':'INR','amount':60000 if t['type']=='education' else 180000,'status':'unpaid','synthetic':True})
    by_tenant={t['id']:[] for t in tenants}
    for u in users:
        if u['role']=='student':by_tenant[u['tenant_id']].append(u)
    for p in (x for x in users if x['role']=='parent'):
        ss=by_tenant[p['tenant_id']]
        if ss: parent_links.append({'tenant_id':p['tenant_id'],'parent_id':p['id'],'student_id':ss[len(parent_links)%len(ss)]['id']})
    for e in enrollments:
        a=next(x for x in assessments if x['course_id']==e['course_id'])
        attempts.append({'id':uid('attempt',e['id']),'tenant_id':e['tenant_id'],'assessment_id':a['id'],'student_id':e['student_id'],'score':rng.randrange(30,101),'status':['submitted','graded','pending_review'][rng.randrange(3)]})
    for name,rows in locals().copy().items():
        if name in ('tenants','users','courses','enrollments','attendance','assessments','attempts','games','ai_requests','proctoring','invoices','parent_links'):write(root,name,rows)
    print('Generated fictional JSON fixtures in',root)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='synthetic-data');p.add_argument('--students',type=int,default=2000);args=p.parse_args();generate(Path(args.output),args.students)
