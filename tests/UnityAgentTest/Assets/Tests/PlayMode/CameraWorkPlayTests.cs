using System.Collections;
using CameraWorks;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace DarumaPPAP.UnityAgent.Tests
{
    public sealed class CameraWorkPlayTests
    {
        private GameObject _cameraObject;

        [UnityTest]
        public IEnumerator RunsSequentialPhasesToCompletion()
        {
            _cameraObject = new GameObject("Camera Work Play Test");
            _cameraObject.AddComponent<Camera>();
            var work = _cameraObject.AddComponent<CameraWork>();
            var cut = new S_CAMERA_CUT(0, "右パン→ドリーイン", 1, new[]
            {
                new S_CAMERA_PHASE(E_CAMERA_MOVE.PanRight),
                new S_CAMERA_PHASE(E_CAMERA_MOVE.DollyIn)
            });

            work.Play(cut);
            Assert.That(work.IsPlaying, Is.True);
            yield return new WaitForSeconds(3.25f);
            Assert.That(work.IsPlaying, Is.False);
            Assert.That(work.PhaseIndex, Is.EqualTo(2));
            Assert.That(_cameraObject.transform.position.sqrMagnitude, Is.GreaterThan(1f));
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            if (_cameraObject != null)
            {
                Object.Destroy(_cameraObject);
            }

            yield return null;
        }
    }
}
