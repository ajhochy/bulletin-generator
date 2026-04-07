// ─── Church constants ─────────────────────────────────────────────────────────
const WELCOME_ITEMS = [
  'Nursery (0–2 yrs) is available off the NE corner of the courtyard.',
  'Mother/Infant Room is available off the foyer with a live feed of the service.',
  'Nursing Mothers with Toddlers Room is available and located next to the nursery.',
  'Family Room is located off the foyer with books/toys for toddlers and preschoolers. Live feed of the service is available.',
];

const STAFF_DEFAULT = [
  { name: 'Jane Example',          role: 'Lead Pastor',                         email: 'pastor@example.org'            },
  { name: 'John Example',          role: 'Pastor of Congregational Life',       email: 'care@example.org'              },
  { name: 'Jordan Example',        role: 'Pastor of Visitation',                email: 'visitation@example.org'        },
  { name: 'Taylor Example',        role: 'Director of Music & Worship',         email: 'worship@example.org'           },
  { name: 'Morgan Example',        role: 'Director of Youth & Technology',      email: 'youth@example.org'             },
  { name: 'Casey Example',         role: 'Youth Ministries Administrator',      email: 'students@example.org'          },
  { name: 'Riley Example',         role: 'Director of Youth Discipleship',      email: 'discipleship@example.org'      },
  { name: 'Alex Example',          role: "Co-Director of Children's Ministry",  email: 'children@example.org'          },
  { name: 'Sam Example',           role: "Co-Director of Children's Ministry",  email: 'kids@example.org'              },
  { name: 'Jamie Example',         role: 'Church Administrator',                email: 'office@example.org'            },
  { name: 'Avery Example',         role: 'Facilities Maintenance Manager',      email: 'facilities@example.org'        },
  { name: 'Drew Example',          role: 'Administrative Assistant',            email: 'info@example.org'              },
  { name: 'Parker Example',        role: 'Administrative Assistant',            email: 'info@example.org'              },
  { name: 'Cameron Example',       role: 'Custodian',                           email: ''                              },
];
const STAFF_KEY = 'worshipStaffData';

function saveStaffData() {
  apiFetch('/api/settings', 'POST', { staffData }).catch(err => setStatus('Staff save failed: ' + (err.message || err), 'error'));
}

let staffData = STAFF_DEFAULT.map(s => ({ ...s }));  // populated from server at startup

function renderStaffEditor() {
  const container = document.getElementById('staff-editor');
  if (!container) return;
  container.innerHTML = '';

  staffData.forEach((person, idx) => {
    const row = document.createElement('div');
    row.className = 'staff-ed-row';

    const nameIn  = document.createElement('input');
    const roleIn  = document.createElement('input');
    const emailIn = document.createElement('input');
    [nameIn, roleIn, emailIn].forEach((inp, i) => {
      inp.type = 'text';
      inp.className = 'staff-ed-input';
      inp.value = [person.name, person.role, person.email][i];
      inp.placeholder = ['Name', 'Role / Title', 'Email'][i];
      inp.addEventListener('input', () => {
        staffData[idx].name  = nameIn.value;
        staffData[idx].role  = roleIn.value;
        staffData[idx].email = emailIn.value;
        saveStaffData();
        schedulePreviewUpdate();
      });
    });

    const upBtn  = document.createElement('button');
    upBtn.className  = 'icon-btn';
    upBtn.title      = 'Move up';
    upBtn.textContent = '↑';
    upBtn.disabled   = idx === 0;
    upBtn.addEventListener('click', () => {
      if (idx === 0) return;
      [staffData[idx - 1], staffData[idx]] = [staffData[idx], staffData[idx - 1]];
      saveStaffData(); renderStaffEditor(); schedulePreviewUpdate();
    });

    const downBtn  = document.createElement('button');
    downBtn.className  = 'icon-btn';
    downBtn.title      = 'Move down';
    downBtn.textContent = '↓';
    downBtn.disabled   = idx === staffData.length - 1;
    downBtn.addEventListener('click', () => {
      if (idx >= staffData.length - 1) return;
      [staffData[idx], staffData[idx + 1]] = [staffData[idx + 1], staffData[idx]];
      saveStaffData(); renderStaffEditor(); schedulePreviewUpdate();
    });

    const delBtn  = document.createElement('button');
    delBtn.className  = 'icon-btn danger';
    delBtn.title      = 'Remove';
    delBtn.textContent = '×';
    delBtn.addEventListener('click', () => {
      staffData.splice(idx, 1);
      saveStaffData(); renderStaffEditor(); schedulePreviewUpdate();
    });

    row.appendChild(nameIn);
    row.appendChild(roleIn);
    row.appendChild(emailIn);
    row.appendChild(upBtn);
    row.appendChild(downBtn);
    row.appendChild(delBtn);
    container.appendChild(row);
  });

  const staffForceBreakBtn = document.createElement('button');
  staffForceBreakBtn.className = 'vol-add-link';
  staffForceBreakBtn.style.cssText = 'color:var(--muted); display:block; margin:0.4rem 0;';
  staffForceBreakBtn.textContent = breakBeforeStaff
    ? '\u2193 Staff on same page as previous'
    : '\u2191 Start staff on new page';
  staffForceBreakBtn.addEventListener('click', () => {
    breakBeforeStaff = !breakBeforeStaff;
    renderStaffEditor();
    schedulePreviewUpdate();
    scheduleProjectPersist();
  });
  container.appendChild(staffForceBreakBtn);
}

document.addEventListener('DOMContentLoaded', () => {
  const addBtn = document.getElementById('staff-add-btn');
  if (addBtn) addBtn.addEventListener('click', () => {
    staffData.push({ name: '', role: '', email: '' });
    saveStaffData();
    renderStaffEditor();
    // Focus the name field of the new row
    const rows = document.querySelectorAll('#staff-editor .staff-ed-row');
    if (rows.length) rows[rows.length - 1].querySelector('.staff-ed-input').focus();
  });
  renderStaffEditor();
});

/// ─── Split lyrics from copyright (last paragraph if it looks like copyright) ──
function splitLyricsCopyright(detail) {
  const paras = detail.split(/\n\n/);
  const last = paras[paras.length - 1];
  const attributionRe = /ccli|©|\bpublic domain\b|license\s*#|trinity hymnal|psalter hymnal|lift up your hearts|luyh|hymn\s*#|th\s*#|luyh\s*#/i;
  if (paras.length > 1 && attributionRe.test(last)) {
    return { body: paras.slice(0, -1).join('\n\n'), copyright: last };
  }
  return { body: detail, copyright: '' };
}

