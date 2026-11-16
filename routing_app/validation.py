"""Explain partition failures before starting expensive routing work."""


def partition_failure(partition):
    if partition.get('status')!='FAILED':return None
    errors=[str(f['message']) for f in partition.get('findings',[])
        if f.get('severity')=='error' and f.get('message')]
    detail='; '.join(errors[:3]) or 'Review the failed geometry and ownership checks.'
    day=partition.get('day','Collection day').title()
    return f'{day} service areas failed validation: {detail} Open Service areas > Checks before generating truck routes.'
