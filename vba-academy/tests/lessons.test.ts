import { LESSONS, LEVELS } from '../src/content/lessons';
import { createWorkbook, runLesson } from '../src/lib/runner';

async function main() {
  let ok = 0;
  const problems: string[] = [];

  for (const lesson of LESSONS) {
    const wb = createWorkbook(lesson);
    const result = await runLesson(lesson.solution, lesson, wb, {
      onInputBox: async (_p, _t, def) => def,
    });
    if (!result.ok) {
      problems.push(`${lesson.id} "${lesson.title}" → ERROR บรรทัด ${result.error?.line}: ${result.error?.message}`);
      continue;
    }
    const failed = result.tasks.filter((t) => !t.passed);
    if (failed.length) {
      problems.push(`${lesson.id} "${lesson.title}" → เฉลยไม่ผ่าน: ${failed.map((f) => f.label).join(' | ')}`);
      continue;
    }
    // ตรวจว่าโค้ดตั้งต้นต้อง "ยังไม่ผ่าน" (ไม่งั้นบทเรียนไม่มีอะไรให้ทำ)
    const wb2 = createWorkbook(lesson);
    const starterResult = await runLesson(lesson.starter, lesson, wb2, {
      onInputBox: async (_p, _t, def) => def,
    });
    if (starterResult.allPassed && lesson.id !== 'l1-1') {
      problems.push(`${lesson.id} "${lesson.title}" → โค้ดตั้งต้นผ่านหมดแล้ว ไม่มีอะไรให้ผู้เรียนทำ`);
      continue;
    }
    ok++;
  }

  const levelIds = new Set(LEVELS.map((l) => l.id));
  for (const lesson of LESSONS) {
    if (!levelIds.has(lesson.level)) problems.push(`${lesson.id} อ้างด่านที่ไม่มีอยู่: ${lesson.level}`);
    if (!lesson.narration.trim()) problems.push(`${lesson.id} ไม่มีบทพากย์`);
    if (!lesson.tasks.length) problems.push(`${lesson.id} ไม่มีภารกิจ`);
  }

  console.log(`\n📚 บทเรียนทั้งหมด ${LESSONS.length} บท / เฉลยผ่าน ${ok} บท`);
  if (problems.length) {
    console.log('\nปัญหาที่พบ:');
    problems.forEach((p) => console.log(' - ' + p));
    process.exit(1);
  } else {
    console.log('✅ ทุกบทเรียนเฉลยถูกต้อง และโค้ดตั้งต้นยังมีโจทย์ให้ทำ');
  }
}

main();
