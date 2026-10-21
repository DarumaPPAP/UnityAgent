using NUnit.Framework;
namespace UnityAgent.AdaptiveFixture.Tests
{
    public sealed class MultiplierTests
    {
        [Test]
        public void Multiplies()
        {
            Assert.That(Multiplier.Multiply(3, 2), Is.EqualTo(6));
            Assert.That(Multiplier.Multiply(-3, 2), Is.EqualTo(-6));
            Assert.That(Multiplier.Multiply(0, 4), Is.EqualTo(0));
        }
    }
}
