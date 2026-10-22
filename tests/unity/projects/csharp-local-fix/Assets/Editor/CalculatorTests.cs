using NUnit.Framework;
namespace UnityAgent.AdaptiveFixture.Tests
{
    public sealed class CalculatorTests
    {
        [Test]
        public void AddReturnsSum()
        {
            Assert.That(Calculator.Add(3, 2), Is.EqualTo(5));
            Assert.That(Calculator.Add(-3, 2), Is.EqualTo(-1));
            Assert.That(Calculator.Add(0, 0), Is.EqualTo(0));
        }
    }
}
