import sys
sys.path.insert(0, '.')
import auto_push as ap

name = '川原涼'
venue = '蒲郡'
c = '1'

cm = ap.MASTER.get('course_master', {})
vc_master = ap.MASTER.get('venue_course_master', {})
vc = vc_master.get(name, {}).get(venue, {}).get(c)
cmc = cm.get(name, {}).get(c)

print('cmc reliable:', cmc.get('reliable') if cmc else None)
print('vc reliable:', vc.get('reliable') if vc else None)

has_personal_data = (
    (cmc is not None and cmc.get('reliable', False))
    or (vc is not None and vc.get('reliable', False))
)
print('has_personal_data:', has_personal_data)