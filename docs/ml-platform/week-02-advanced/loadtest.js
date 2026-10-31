import http from 'k6/http';
export const options = {
  scenarios: {constant: {executor: 'constant-arrival-rate', rate: Number(__ENV.RATE||20), timeUnit: '1s', duration: __ENV.DURATION||'60s', preAllocatedVUs: 40, maxVUs: 120}}
};
export default function() {
  http.get((__ENV.BASE_URL||'http://localhost:8080') + '/work?n=' + (__ENV.N||120000), {timeout:'10s'});
}
